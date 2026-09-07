from __future__ import annotations

import os
import struct
from collections.abc import Callable, Mapping
from dataclasses import dataclass, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

from telecraft.mtproto.gzip_utils import decompress_limited

VECTOR_CONSTRUCTOR_ID = 0x1CB5C415

# MTProto core "special" constructors which are not present in the generated schema.
# These are still sent by the server and must be parsed manually.
_RPC_RESULT_CONSTRUCTOR_ID = -212046591  # 0xF35C6D01
_MSG_CONTAINER_CONSTRUCTOR_ID = 1945237724  # 0x73F1F8DC
_GZIP_PACKED_CONSTRUCTOR_ID = 812830625  # 0x3072CFA1
_POLL_CONSTRUCTOR_ID = -1771164225  # 0x9662A35F (layer 228)
_POLL_RESULTS_CONSTRUCTOR_ID = -1166298786  # 0xBA2C595E (layer 228)
_LEGACY_POLL_CONSTRUCTOR_ID = 1484026161  # 0x58747131
_LEGACY_POLL_RESULTS_CONSTRUCTOR_ID = 2061444128  # 0x7ADF2420
_MESSAGE_MEDIA_POLL_CONSTRUCTOR_ID = 2000637542  # 0x773F4E66 (layer 228)


@dataclass(slots=True)
class RpcResult:
    req_msg_id: int
    result: Any


@dataclass(slots=True)
class ContainerMessage:
    msg_id: int
    seqno: int
    obj: Any


@dataclass(slots=True)
class MsgContainer:
    messages: list[ContainerMessage]


class TLCodecError(Exception):
    pass


class UnsafeTLPayloadError(TLCodecError):
    """A bounded TL payload cannot be acknowledged or parsed further safely."""


class TrailingTLDataError(UnsafeTLPayloadError):
    def __init__(self, *, path: str, position: int, trailing_bytes: int) -> None:
        self.path = str(path)
        self.position = int(position)
        self.trailing_bytes = int(trailing_bytes)
        self.constructor_id: int | None = None
        self.expected_type: str | None = None
        super().__init__(
            f"Trailing bytes after bounded TL object at {path} "
            f"(pos={position}, trailing={trailing_bytes})"
        )


class UnknownConstructorError(UnsafeTLPayloadError):
    """A TL object cannot be bounded safely because its wire layout is unknown."""

    def __init__(
        self,
        *,
        constructor_id: int,
        expected_type: str | None,
        path: str,
        position: int,
    ) -> None:
        self.constructor_id = int(constructor_id)
        self.expected_type = expected_type
        self.path = path
        self.position = int(position)
        unsigned_id = self.constructor_id & 0xFFFFFFFF
        type_note = f" for {expected_type}" if expected_type else ""
        super().__init__(
            f"Unknown constructor id: {self.constructor_id} (0x{unsigned_id:08x})"
            f"{type_note} at {path} (pos={position})"
        )


class UntypedVectorError(UnsafeTLPayloadError):
    """A bare Vector constructor was encountered without its schema element type."""

    def __init__(self, *, path: str, position: int) -> None:
        self.constructor_id = VECTOR_CONSTRUCTOR_ID
        self.expected_type: str | None = None
        self.path = str(path)
        self.position = int(position)
        super().__init__(
            f"Cannot decode bare Vector without its schema element type at {path} (pos={position})"
        )


def _pad4(n: int) -> int:
    return (4 - (n % 4)) % 4


def _debug_dump_bad_tl_payload(data: bytes, *, prefix: str = "bad_payload") -> None:
    if os.getenv("TELECRAFT_DEBUG_DUMP_TL") != "1":
        return
    root = Path(os.getenv("TELECRAFT_DEBUG_TL_DIR", "reports/debug_tl"))
    root.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    suffix = os.urandom(2).hex()
    path = root / f"{prefix}_{ts}_{suffix}.bin"
    path.write_bytes(data)


class TLWriter:
    __slots__ = ("_buf",)

    def __init__(self) -> None:
        self._buf = bytearray()

    def to_bytes(self) -> bytes:
        return bytes(self._buf)

    def write_int(self, value: int) -> None:
        self._buf += struct.pack("<i", value)

    def write_uint(self, value: int) -> None:
        self._buf += struct.pack("<I", value)

    def write_long(self, value: int) -> None:
        self._buf += struct.pack("<q", value)

    def write_double(self, value: float) -> None:
        self._buf += struct.pack("<d", value)

    def write_bytes(self, data: bytes) -> None:
        ln = len(data)
        if ln < 254:
            self._buf.append(ln)
            self._buf += data
            self._buf += b"\x00" * _pad4(1 + ln)
            return

        self._buf.append(254)
        self._buf += struct.pack("<I", ln)[:3]
        self._buf += data
        self._buf += b"\x00" * _pad4(4 + ln)

    def write_string(self, value: str | bytes | bytearray) -> None:
        if isinstance(value, (bytes, bytearray)):
            self.write_bytes(bytes(value))
            return
        if isinstance(value, str):
            self.write_bytes(value.encode("utf-8"))
            return
        raise TLCodecError("string value must be str/bytes/bytearray")

    def write_object(self, obj: Any) -> None:
        # TLObject/TLRequest both have TL_ID/TL_PARAMS as ClassVar.
        if bool(getattr(obj, "TL_INBOUND_ONLY", False)):
            raise TLCodecError(
                f"Inbound-only TL constructor cannot be serialized: "
                f"{getattr(obj, 'TL_NAME', type(obj).__name__)}"
            )
        tl_id = getattr(obj, "TL_ID", None)
        if not isinstance(tl_id, int) or tl_id == 0:
            raise TLCodecError(f"Object has invalid TL_ID: {obj!r}")
        self.write_int(tl_id)
        self._write_params(obj)

    def _write_params(self, obj: Any) -> None:
        tl_params = getattr(obj, "TL_PARAMS", None)
        if tl_params is None:
            return
        if not isinstance(tl_params, tuple):
            raise TLCodecError("Invalid TL_PARAMS")

        # Compute flags (for any param declared as '#').
        flags_values: dict[str, int] = {}
        for field, type_expr in tl_params:
            if type_expr == "#":
                flags_values[field] = 0

        if flags_values:
            for field, type_expr in tl_params:
                # e.g. flags.1?string
                if "?" not in type_expr or "." not in type_expr:
                    continue
                before_q, inner = type_expr.split("?", 1)
                if "." not in before_q:
                    continue
                flags_name, bit_s = before_q.split(".", 1)
                if flags_name not in flags_values:
                    continue
                try:
                    bit = int(bit_s)
                except ValueError:
                    continue
                value = getattr(obj, field, None)
                if inner == "true":
                    present = bool(value)
                else:
                    present = value is not None
                if present:
                    flags_values[flags_name] |= 1 << bit

        for field, type_expr in tl_params:
            if type_expr == "#":
                self.write_int(flags_values.get(field, int(getattr(obj, field, 0))))
                continue

            # Optional flags field: flags.N?T
            if "?" in type_expr and "." in type_expr.split("?", 1)[0]:
                before_q, inner = type_expr.split("?", 1)
                flags_name, bit_s = before_q.split(".", 1)
                bit_opt: int | None
                try:
                    bit_opt = int(bit_s)
                except ValueError:
                    bit_opt = None
                if bit_opt is not None and (flags_values.get(flags_name, 0) & (1 << bit_opt)) == 0:
                    continue
                if inner == "true":
                    continue
                value = getattr(obj, field)
                self.write_value(inner, value)
                continue

            value = getattr(obj, field)
            self.write_value(type_expr, value)

    def write_value(self, type_expr: str, value: Any) -> None:
        type_expr = type_expr.strip()
        if type_expr == "int":
            self.write_int(int(value))
            return
        if type_expr == "long":
            self.write_long(int(value))
            return
        if type_expr == "int128":
            if isinstance(value, int):
                value = int(value).to_bytes(16, "little", signed=False)
            if not isinstance(value, (bytes, bytearray)) or len(value) != 16:
                raise TLCodecError("int128 must be 16 bytes (or int convertible to 16 bytes)")
            self._buf += bytes(value)
            return
        if type_expr == "int256":
            if isinstance(value, int):
                value = int(value).to_bytes(32, "little", signed=False)
            if not isinstance(value, (bytes, bytearray)) or len(value) != 32:
                raise TLCodecError("int256 must be 32 bytes (or int convertible to 32 bytes)")
            self._buf += bytes(value)
            return
        if type_expr == "double":
            self.write_double(float(value))
            return
        if type_expr == "string":
            self.write_string(value)
            return
        if type_expr == "bytes":
            if not isinstance(value, (bytes, bytearray)):
                raise TLCodecError("bytes value must be bytes/bytearray")
            self.write_bytes(bytes(value))
            return
        if type_expr == "Bool":
            # Encoded as constructor id
            self.write_int(-1720552011 if bool(value) else -1132882121)
            return
        if type_expr.startswith("Vector<") and type_expr.endswith(">"):
            inner = type_expr[len("Vector<") : -1].strip()
            if not isinstance(value, list):
                raise TLCodecError("Vector value must be a list")
            self.write_int(VECTOR_CONSTRUCTOR_ID)
            self.write_int(len(value))
            for item in value:
                self.write_value(inner, item)
            return

        # Assume TLObject/TLRequest
        if is_dataclass(value) or hasattr(value, "TL_ID"):
            self.write_object(value)
            return
        raise TLCodecError(f"Unsupported type expression: {type_expr!r}")


class TLReader:
    __slots__ = ("_data", "_pos", "_rpc_result_types")

    def __init__(
        self,
        data: bytes,
        *,
        rpc_result_types: Mapping[int, str] | None = None,
    ) -> None:
        self._data = data
        self._pos = 0
        self._rpc_result_types = rpc_result_types or {}

    def _read(self, n: int) -> bytes:
        if self._pos + n > len(self._data):
            raise TLCodecError("Unexpected EOF")
        out = self._data[self._pos : self._pos + n]
        self._pos += n
        return out

    def _remaining(self) -> int:
        return len(self._data) - self._pos

    def ensure_eof(self, *, path: str) -> None:
        trailing = self._remaining()
        if trailing:
            raise TrailingTLDataError(
                path=path,
                position=self._pos,
                trailing_bytes=trailing,
            )

    def _peek_int(self) -> int:
        if self._remaining() < 4:
            raise TLCodecError("Unexpected EOF")
        return int(struct.unpack_from("<i", self._data, self._pos)[0])

    def _read_rpc_result_value(self, *, req_msg_id: int, path: str) -> Any:
        """Decode the final ``rpc_result`` field using its request result type.

        Telegram's schema declares this field as the generic ``Object`` type,
        but bare vectors do not carry their element type on the wire.  The
        request's ``TL_RESULT`` is therefore required to consume them safely.
        Boxed errors remain self-describing and must be handled before applying
        the expected result type.
        """

        expected_type = self._rpc_result_types.get(int(req_msg_id))
        if expected_type is None:
            return self.read_object(path=path)

        return self._read_expected_rpc_result_value(
            expected_type=expected_type,
            path=path,
        )

    def _read_expected_rpc_result_value(self, *, expected_type: str, path: str) -> Any:
        """Read one typed RPC result, preserving boxed error/wrapper semantics."""

        next_cid = self._peek_int()
        if next_cid == _GZIP_PACKED_CONSTRUCTOR_ID:
            self.read_int()
            return self._read_gzip_packed(path=path, expected_type=expected_type)

        from telecraft.tl.generated.registry import INBOUND_CONSTRUCTORS_BY_ID

        next_cls = INBOUND_CONSTRUCTORS_BY_ID.get(next_cid)
        if getattr(next_cls, "TL_NAME", None) == "rpc_error":
            return self.read_object(path=path)

        if expected_type.startswith("Vector<") and expected_type.endswith(">"):
            return self.read_value(expected_type, path=path)
        return self.read_object(path=path, expected_type=expected_type)

    def _read_gzip_packed(self, *, path: str, expected_type: str | None = None) -> Any:
        packed = self.read_bytes()
        try:
            unpacked = decompress_limited(packed)
        except Exception as e:  # noqa: BLE001
            raise TLCodecError("Failed to decompress gzip_packed payload") from e
        inner = TLReader(unpacked, rpc_result_types=self._rpc_result_types)
        inner_path = f"{path}.gzip_packed"
        if expected_type is None:
            obj = inner.read_object(path=inner_path)
        else:
            # This helper is reached after the gzip constructor has already
            # been consumed from rpc_result.result, so decode the unpacked
            # value according to the originating request while still accepting
            # Telegram's boxed rpc_error response.
            obj = inner._read_expected_rpc_result_value(
                expected_type=expected_type,
                path=inner_path,
            )
        inner.ensure_eof(path=inner_path)
        return obj

    def read_int(self) -> int:
        return int(struct.unpack("<i", self._read(4))[0])

    def read_long(self) -> int:
        return int(struct.unpack("<q", self._read(8))[0])

    def read_double(self) -> float:
        return float(struct.unpack("<d", self._read(8))[0])

    def read_bytes(self) -> bytes:
        first = self._read(1)[0]
        if first < 254:
            ln = first
            data = self._read(ln)
            self._read(_pad4(1 + ln))
            return data
        ln = int.from_bytes(self._read(3), "little")
        data = self._read(ln)
        self._read(_pad4(4 + ln))
        return data

    def read_string(self) -> bytes:
        # TL "string" is stored with the same encoding as TL "bytes" (length + padding).
        # Decoding to text is caller responsibility.
        return self.read_bytes()

    def read_value(self, type_expr: str, *, path: str = "root") -> Any:
        type_expr = type_expr.strip()
        if type_expr == "int":
            return self.read_int()
        if type_expr == "long":
            return self.read_long()
        if type_expr == "int128":
            return self._read(16)
        if type_expr == "int256":
            return self._read(32)
        if type_expr == "double":
            return self.read_double()
        if type_expr == "string":
            return self.read_string()
        if type_expr == "bytes":
            return self.read_bytes()
        if type_expr == "Bool":
            cid = self.read_int()
            if cid == -1720552011:
                return True
            if cid == -1132882121:
                return False
            raise TLCodecError(f"Invalid Bool constructor id: {cid}")
        if type_expr.startswith("Vector<") and type_expr.endswith(">"):
            inner = type_expr[len("Vector<") : -1].strip()
            cid = self.read_int()
            if cid != VECTOR_CONSTRUCTOR_ID:
                raise TLCodecError(f"Invalid vector constructor id: {cid}")
            count = self.read_int()
            if count < 0:
                raise TLCodecError("Negative vector item count")
            return [self.read_value(inner, path=f"{path}[{idx}]") for idx in range(count)]
        # TL object (sum types): read by constructor id.
        return self.read_object(path=path, expected_type=type_expr)

    def _read_poll_for_message_media_poll(self, *, path: str) -> Any:
        from telecraft.tl.generated.types import Poll

        start = self._pos
        cid = self.read_int()
        if cid == _LEGACY_POLL_CONSTRUCTOR_ID:
            self._pos = start
            return self.read_object(path=path, expected_type="Poll")
        if cid != _POLL_CONSTRUCTOR_ID:
            self._pos = start
            return self.read_object(path=path, expected_type="Poll")

        poll_id = self.read_long()
        flags = self.read_int()
        closed = bool(flags & (1 << 0))
        public_voters = bool(flags & (1 << 1))
        multiple_choice = bool(flags & (1 << 2))
        quiz = bool(flags & (1 << 3))
        open_answers = bool(flags & (1 << 6))
        revoting_disabled = bool(flags & (1 << 7))
        shuffle_answers = bool(flags & (1 << 8))
        hide_results_until_close = bool(flags & (1 << 9))
        creator = bool(flags & (1 << 10))
        subscribers_only = bool(flags & (1 << 11))
        question = self.read_value("TextWithEntities", path=f"{path}.question")
        answers = self.read_value("Vector<PollAnswer>", path=f"{path}.answers")

        close_period: int | None = None
        if flags & (1 << 4):
            close_period = self.read_int()

        close_date: int | None = None
        jumped_to_results = False
        if flags & (1 << 5):
            if self._remaining() >= 4 and self._peek_int() == _POLL_RESULTS_CONSTRUCTOR_ID:
                # Compatibility: some payloads advertise close_date but jump
                # directly to pollResults. Such legacy payloads also predate the
                # layer-228 countries/hash tail, so leave the cursor untouched.
                flags &= ~(1 << 5)
                jumped_to_results = True
            else:
                close_date = self.read_int()

        countries_iso2 = None
        hash_value = 0
        if not jumped_to_results:
            if flags & (1 << 12):
                countries_iso2 = self.read_value("Vector<string>", path=f"{path}.countries_iso2")
            hash_value = self.read_long()

        return Poll(
            id=poll_id,
            flags=flags,
            closed=closed,
            public_voters=public_voters,
            multiple_choice=multiple_choice,
            quiz=quiz,
            open_answers=open_answers,
            revoting_disabled=revoting_disabled,
            shuffle_answers=shuffle_answers,
            hide_results_until_close=hide_results_until_close,
            creator=creator,
            subscribers_only=subscribers_only,
            question=question,
            answers=answers,
            close_period=close_period,
            close_date=close_date,
            countries_iso2=countries_iso2,
            hash=hash_value,
        )

    def _read_poll_results_bare(self, *, path: str) -> Any:
        from telecraft.tl.generated.types import PollResults

        flags = self.read_int()
        if flags < 0:
            raise TLCodecError(f"Invalid pollResults flags: {flags}")
        known_flags_mask = (1 << 8) - 1
        if flags & ~known_flags_mask:
            raise TLCodecError(f"Unsupported pollResults flags: {flags}")

        min_value = bool(flags & (1 << 0))
        has_unread_votes = bool(flags & (1 << 6))
        can_view_stats = bool(flags & (1 << 7))
        results = (
            self.read_value("Vector<PollAnswerVoters>", path=f"{path}.results")
            if flags & (1 << 1)
            else None
        )
        total_voters = self.read_int() if flags & (1 << 2) else None
        recent_voters = (
            self.read_value("Vector<Peer>", path=f"{path}.recent_voters")
            if flags & (1 << 3)
            else None
        )
        solution = self.read_value("string", path=f"{path}.solution") if flags & (1 << 4) else None
        solution_entities = (
            self.read_value("Vector<MessageEntity>", path=f"{path}.solution_entities")
            if flags & (1 << 4)
            else None
        )
        solution_media = (
            self.read_value("MessageMedia", path=f"{path}.solution_media")
            if flags & (1 << 5)
            else None
        )

        return PollResults(
            flags=flags,
            min=min_value,
            has_unread_votes=has_unread_votes,
            can_view_stats=can_view_stats,
            results=results,
            total_voters=total_voters,
            recent_voters=recent_voters,
            solution=solution,
            solution_entities=solution_entities,
            solution_media=solution_media,
        )

    def _read_poll_results_for_message_media_poll(self, *, path: str) -> Any:
        candidate = self._peek_int()
        if candidate == _POLL_RESULTS_CONSTRUCTOR_ID:
            self.read_int()
            return self._read_poll_results_bare(path=path)
        if candidate == _LEGACY_POLL_RESULTS_CONSTRUCTOR_ID:
            return self.read_object(path=path, expected_type="PollResults")
        if 0 <= candidate <= ((1 << 8) - 1):
            # Compatibility with captured legacy payloads where pollResults was
            # encoded bare. Only the complete known flags mask is ambiguous with
            # a constructor id; every other value must take the structured object
            # path so UnknownConstructorError is never swallowed or downgraded.
            return self._read_poll_results_bare(path=path)
        return self.read_object(path=path, expected_type="PollResults")

    def _read_message_media_poll(self, *, path: str) -> Any:
        from telecraft.tl.generated.types import MessageMediaPoll

        # Layer 228 added flags and optional attached media. Preserve support for
        # the older captured payload shape, where the Poll constructor followed
        # messageMediaPoll immediately.
        flags = (
            0
            if self._peek_int() in {_POLL_CONSTRUCTOR_ID, _LEGACY_POLL_CONSTRUCTOR_ID}
            else self.read_int()
        )
        poll = self._read_poll_for_message_media_poll(path=f"{path}.poll")
        results = self._read_poll_results_for_message_media_poll(path=f"{path}.results")
        attached_media = (
            self.read_value("MessageMedia", path=f"{path}.attached_media") if flags & 1 else None
        )
        return MessageMediaPoll(
            flags=flags,
            poll=poll,
            results=results,
            attached_media=attached_media,
        )

    def read_object(self, *, path: str = "root", expected_type: str | None = None) -> Any:
        from telecraft.tl.generated._legacy_normalizers import LEGACY_NORMALIZERS_BY_ID
        from telecraft.tl.generated.registry import INBOUND_CONSTRUCTORS_BY_ID, METHODS_BY_ID

        cid_pos = self._pos
        cid = self.read_int()

        if cid == VECTOR_CONSTRUCTOR_ID:
            raise UntypedVectorError(path=path, position=cid_pos)

        # Manual parsing for core MTProto containers/results.
        if cid == _RPC_RESULT_CONSTRUCTOR_ID:
            req_msg_id = self.read_long()
            result = self._read_rpc_result_value(
                req_msg_id=req_msg_id,
                path=f"{path}.rpc_result",
            )
            return RpcResult(req_msg_id=req_msg_id, result=result)

        if cid == _MSG_CONTAINER_CONSTRUCTOR_ID:
            count = self.read_int()
            if count < 0:
                raise TLCodecError("Negative msg_container message count")
            messages: list[ContainerMessage] = []
            for idx in range(count):
                msg_id = self.read_long()
                seqno = self.read_int()
                ln = self.read_int()
                if ln < 0:
                    raise TLCodecError("Negative msg_container message length")
                payload = self._read(ln)
                inner = TLReader(payload, rpc_result_types=self._rpc_result_types)
                inner_path = f"{path}.msg_container[{idx}]"
                obj = inner.read_object(path=inner_path)
                inner.ensure_eof(path=inner_path)
                messages.append(ContainerMessage(msg_id=msg_id, seqno=seqno, obj=obj))
            return MsgContainer(messages=messages)

        if cid == _GZIP_PACKED_CONSTRUCTOR_ID:
            return self._read_gzip_packed(path=path)

        cls = INBOUND_CONSTRUCTORS_BY_ID.get(cid) or METHODS_BY_ID.get(cid)
        if cls is None:
            raise UnknownConstructorError(
                constructor_id=cid,
                expected_type=expected_type,
                path=path,
                position=cid_pos,
            )

        if cid == _MESSAGE_MEDIA_POLL_CONSTRUCTOR_ID:
            return self._read_message_media_poll(path=path)

        tl_params = getattr(cls, "TL_PARAMS", ())
        kwargs: dict[str, Any] = {}

        # Flag words appear in declaration order. Most constructors place them
        # first, but valid layouts such as ``poll`` serialize ``id`` before
        # ``flags``; reading every flag word up front would shift the cursor.
        flags_values: dict[str, int] = {}
        for field, type_expr in tl_params:
            if type_expr == "#":
                flags_values[field] = self.read_int()
                kwargs[field] = flags_values[field]
                continue
            field_path = f"{path}.{getattr(cls, 'TL_NAME', cls.__name__)}.{field}"
            if "?" in type_expr and "." in type_expr.split("?", 1)[0]:
                before_q, inner = type_expr.split("?", 1)
                flags_name, bit_s = before_q.split(".", 1)
                try:
                    bit = int(bit_s)
                except ValueError:
                    bit = None
                if bit is None or (flags_values.get(flags_name, 0) & (1 << bit)) == 0:
                    # flags.N?true: bit not set => field is False (not True)
                    kwargs[field] = False if inner == "true" else None
                    continue
                if inner == "true":
                    kwargs[field] = True
                    continue
                kwargs[field] = self.read_value(inner, path=field_path)
                continue

            kwargs[field] = self.read_value(type_expr, path=field_path)

        decoded = cls(**kwargs)
        normalizer = cast(
            Callable[[Any], Any] | None,
            LEGACY_NORMALIZERS_BY_ID.get(cid),
        )
        return normalizer(decoded) if normalizer is not None else decoded


def dumps(obj: Any) -> bytes:
    w = TLWriter()
    w.write_object(obj)
    return w.to_bytes()


def loads(
    data: bytes,
    *,
    allow_trailing: bool = False,
    rpc_result_types: Mapping[int, str] | None = None,
) -> Any:
    r = TLReader(data, rpc_result_types=rpc_result_types)
    try:
        obj = r.read_object(path="root")
        if not allow_trailing:
            r.ensure_eof(path="root")
    except TLCodecError:
        _debug_dump_bad_tl_payload(data)
        raise
    return obj
