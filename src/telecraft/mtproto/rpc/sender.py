from __future__ import annotations

import asyncio
import logging
import math
import re
import struct
import time
from dataclasses import dataclass, field
from typing import Any, Protocol, cast

from telecraft.mtproto.core.msg_id import MsgIdGenerator
from telecraft.mtproto.core.state import MtprotoState
from telecraft.mtproto.gzip_utils import decompress_limited
from telecraft.tl.codec import (
    MsgContainer,
    RpcResult,
    TLCodecError,
    UnknownConstructorError,
    UnsafeTLPayloadError,
    loads,
)
from telecraft.tl.generated.types import (
    BadMsgNotification,
    BadServerSalt,
    MsgResendReq,
    MsgsAck,
    NewSessionCreated,
    Pong,
    RpcError,
)

logger = logging.getLogger(__name__)

# Pattern to extract wait time from FLOOD_WAIT_X, SLOWMODE_WAIT_X, etc.
_WAIT_PATTERN = re.compile(r"(?:FLOOD_WAIT|SLOWMODE_WAIT|FLOOD_PREMIUM_WAIT)_(\d+)")
_MIGRATE_PATTERN = re.compile(r"^(PHONE|NETWORK|USER|FILE)_MIGRATE_(\d+)$")
_RPC_RESULT_CONSTRUCTOR_ID = -212046591  # 0xF35C6D01
_MSG_CONTAINER_CONSTRUCTOR_ID = 1945237724  # 0x73F1F8DC
_GZIP_PACKED_CONSTRUCTOR_ID = 812830625  # 0x3072CFA1
_RECEIVED_MSG_ID_CACHE_SIZE = 1024
_SERVER_MSG_ID_MAX_FUTURE_SECONDS = 30
_SERVER_MSG_ID_MAX_PAST_SECONDS = 300


class PacketTransport(Protocol):
    async def send(self, payload: bytes) -> None: ...
    async def recv(self) -> bytes: ...


class RpcSenderError(Exception):
    pass


class FloodWaitError(RpcSenderError):
    """Raised when Telegram returns a FLOOD_WAIT or SLOWMODE_WAIT error."""

    def __init__(self, *, code: int, message: str, wait_seconds: int) -> None:
        super().__init__(f"FLOOD_WAIT {wait_seconds}s: {message}")
        self.code = code
        self.message = message
        self.wait_seconds = wait_seconds


class RpcErrorException(RpcSenderError):
    def __init__(self, *, code: int, message: str) -> None:
        super().__init__(f"RPC_ERROR {code}: {message}")
        self.code = code
        self.message = message


class DcMigrateError(RpcErrorException):
    """Telegram rejected an RPC because it must be repeated on another DC."""

    def __init__(self, *, code: int, message: str, kind: str, dc_id: int) -> None:
        super().__init__(code=code, message=message)
        self.kind = kind
        self.dc_id = dc_id


class RpcDecodeError(RpcSenderError):
    """Raised when a response payload cannot be decoded into TL objects."""

    def __init__(
        self,
        message: str,
        *,
        constructor_id: int | None = None,
        expected_type: str | None = None,
        path: str | None = None,
        position: int | None = None,
        requires_reconnect: bool = False,
    ) -> None:
        super().__init__(message)
        self.constructor_id = constructor_id
        self.expected_type = expected_type
        self.path = path
        self.position = position
        self.requires_reconnect = bool(requires_reconnect)
        # A failed RPC may have executed before its response became undecodable.
        # Outer bot runners must never replay it automatically.
        self.retryable = not self.requires_reconnect

    @classmethod
    def from_decode_failure(
        cls,
        error: Exception,
        *,
        outer_msg_id: int | None,
        default_path: str = "root",
    ) -> RpcDecodeError:
        constructor_id = getattr(error, "constructor_id", None)
        expected_type = getattr(error, "expected_type", None)
        path = getattr(error, "path", None)
        if not isinstance(path, str):
            path = default_path
        position = getattr(error, "position", None)
        envelope = (
            f"outer_msg_id={outer_msg_id}"
            if outer_msg_id is not None
            else "outer_msg_id=unavailable"
        )
        return cls(
            "The MTProto connection returned an undecodable authenticated protocol payload and "
            "cannot "
            f"continue ({envelope}): {error}",
            constructor_id=int(constructor_id) if isinstance(constructor_id, int) else None,
            expected_type=str(expected_type) if isinstance(expected_type, str) else None,
            path=str(path) if isinstance(path, str) else None,
            position=int(position) if isinstance(position, int) else None,
            requires_reconnect=True,
        )

    @classmethod
    def from_unsafe_payload(
        cls,
        error: UnsafeTLPayloadError,
        *,
        outer_msg_id: int,
    ) -> RpcDecodeError:
        return cls.from_decode_failure(error, outer_msg_id=outer_msg_id)

    @classmethod
    def from_unknown_constructor(
        cls,
        error: UnknownConstructorError,
        *,
        outer_msg_id: int,
    ) -> RpcDecodeError:
        return cls.from_unsafe_payload(error, outer_msg_id=outer_msg_id)

    @property
    def fingerprint(self) -> tuple[int, str] | None:
        if self.constructor_id is None or self.path is None:
            return None
        return int(self.constructor_id), str(self.path)


def parse_flood_wait_seconds(message: str) -> int | None:
    """
    Parse FLOOD_WAIT_X / SLOWMODE_WAIT_X / FLOOD_PREMIUM_WAIT_X messages.
    Returns the wait time in seconds, or None if not a flood wait error.
    """
    m = _WAIT_PATTERN.search(message)
    if m:
        return int(m.group(1))
    return None


@dataclass(slots=True)
class ReceivedMessage:
    msg_id: int
    seqno: int
    obj: Any


@dataclass(frozen=True, slots=True)
class ReceiverTerminated:
    """Terminal receiver state forwarded to the client update consumer."""

    error: RpcSenderError

    @property
    def requires_reconnect(self) -> bool:
        return bool(getattr(self.error, "requires_reconnect", False))

    @property
    def constructor_id(self) -> int | None:
        value = getattr(self.error, "constructor_id", None)
        return int(value) if isinstance(value, int) else None

    @property
    def expected_type(self) -> str | None:
        value = getattr(self.error, "expected_type", None)
        return str(value) if isinstance(value, str) else None

    @property
    def path(self) -> str | None:
        value = getattr(self.error, "path", None)
        return str(value) if isinstance(value, str) else None

    @property
    def position(self) -> int | None:
        value = getattr(self.error, "position", None)
        return int(value) if isinstance(value, int) else None


@dataclass(frozen=True, slots=True)
class UpdatesRecoveryRequired:
    """Signal that the updates consumer must recover with ``updates.getDifference``."""

    reason: str
    requires_reconnect: bool = False
    constructor_id: int | None = None
    expected_type: str | None = None
    path: str | None = None
    position: int | None = None

    @classmethod
    def from_decode_error(cls, error: RpcDecodeError) -> UpdatesRecoveryRequired:
        return cls(
            reason="unknown_constructor",
            requires_reconnect=error.requires_reconnect,
            constructor_id=error.constructor_id,
            expected_type=error.expected_type,
            path=error.path,
            position=error.position,
        )

    @property
    def fingerprint(self) -> tuple[int, str] | None:
        if self.constructor_id is None or self.path is None:
            return None
        return int(self.constructor_id), str(self.path)


def _parse_inner_message(inner: bytes) -> tuple[int, int, bytes]:
    if len(inner) < 16:
        raise RpcSenderError("Inner message too short")
    msg_id = struct.unpack_from("<q", inner, 0)[0]
    seqno = struct.unpack_from("<i", inner, 8)[0]
    msg_len = struct.unpack_from("<i", inner, 12)[0]
    if msg_len < 0:
        raise RpcSenderError("Negative message length")
    if msg_len % 4 != 0:
        raise RpcSenderError("Message length must be divisible by 4")
    end = 16 + msg_len
    if end > len(inner):
        raise RpcSenderError("Message length exceeds decrypted payload")
    if end != len(inner):
        raise RpcSenderError("Unexpected trailing bytes after decrypted message body")
    return msg_id, seqno, inner[16:end]


def _i64_to_le_bytes(x: int) -> bytes:
    return (int(x) & ((1 << 64) - 1)).to_bytes(8, "little", signed=False)


def _read_tl_bytes_from(payload: bytes, *, start: int) -> tuple[bytes, int]:
    if start >= len(payload):
        raise ValueError("Unexpected EOF while reading TL bytes")
    first = payload[start]
    if first < 254:
        ln = first
        p = start + 1
        end = p + ln
        if end > len(payload):
            raise ValueError("Unexpected EOF in TL bytes (short)")
        pad = (4 - ((1 + ln) % 4)) % 4
        end += pad
        if end > len(payload):
            raise ValueError("Unexpected EOF in TL bytes padding")
        return payload[p : p + ln], end

    if start + 4 > len(payload):
        raise ValueError("Unexpected EOF in TL bytes header")
    ln = int.from_bytes(payload[start + 1 : start + 4], "little")
    p = start + 4
    end = p + ln
    if end > len(payload):
        raise ValueError("Unexpected EOF in TL bytes (long)")
    pad = (4 - ((4 + ln) % 4)) % 4
    end += pad
    if end > len(payload):
        raise ValueError("Unexpected EOF in TL bytes padding (long)")
    return payload[p : p + ln], end


def _collect_req_msg_ids(payload: bytes, out: set[int], *, depth: int = 0) -> None:
    if depth > 8 or len(payload) < 4:
        return
    cid = int(struct.unpack_from("<i", payload, 0)[0])

    if cid == _RPC_RESULT_CONSTRUCTOR_ID:
        if len(payload) >= 12:
            out.add(int(struct.unpack_from("<q", payload, 4)[0]))
        return

    if cid == _MSG_CONTAINER_CONSTRUCTOR_ID:
        if len(payload) < 8:
            return
        count = int(struct.unpack_from("<i", payload, 4)[0])
        if count < 0:
            return
        pos = 8
        for _ in range(count):
            if pos + 16 > len(payload):
                return
            msg_len = int(struct.unpack_from("<i", payload, pos + 12)[0])
            if msg_len < 0:
                return
            start = pos + 16
            end = start + msg_len
            if end > len(payload):
                return
            _collect_req_msg_ids(payload[start:end], out, depth=depth + 1)
            pos = end
        return

    if cid == _GZIP_PACKED_CONSTRUCTOR_ID:
        try:
            packed, _ = _read_tl_bytes_from(payload, start=4)
            unpacked = decompress_limited(packed)
        except Exception:  # noqa: BLE001
            return
        _collect_req_msg_ids(unpacked, out, depth=depth + 1)


def extract_req_msg_ids_from_payload(payload: bytes) -> set[int]:
    req_msg_ids: set[int] = set()
    try:
        _collect_req_msg_ids(payload, req_msg_ids)
    except Exception:  # noqa: BLE001
        logger.debug("Failed to extract req_msg_id from undecodable payload", exc_info=True)
    return req_msg_ids


def _validate_nested_message_lengths(payload: bytes, *, depth: int = 0) -> None:
    """Validate message lengths inside containers, including gzip-wrapped containers."""

    if depth > 8:
        raise RpcSenderError("Incoming message nesting is too deep")
    if len(payload) < 4:
        return
    constructor_id = int(struct.unpack_from("<i", payload, 0)[0])
    if constructor_id == _MSG_CONTAINER_CONSTRUCTOR_ID:
        if len(payload) < 8:
            raise RpcSenderError("Truncated msg_container header")
        count = int(struct.unpack_from("<i", payload, 4)[0])
        if count < 0:
            raise RpcSenderError("Negative msg_container message count")
        position = 8
        for _ in range(count):
            if position + 16 > len(payload):
                raise RpcSenderError("Truncated msg_container message header")
            msg_len = int(struct.unpack_from("<i", payload, position + 12)[0])
            if msg_len < 0:
                raise RpcSenderError("Negative msg_container message length")
            if msg_len % 4 != 0:
                raise RpcSenderError("msg_container message length must be divisible by 4")
            start = position + 16
            end = start + msg_len
            if end > len(payload):
                raise RpcSenderError("msg_container message exceeds payload")
            _validate_nested_message_lengths(payload[start:end], depth=depth + 1)
            position = end
        if position != len(payload):
            raise RpcSenderError("Unexpected trailing bytes in msg_container")
        return

    if constructor_id == _GZIP_PACKED_CONSTRUCTOR_ID:
        try:
            packed, end = _read_tl_bytes_from(payload, start=4)
            unpacked = decompress_limited(packed)
        except Exception as exc:  # noqa: BLE001
            raise RpcSenderError("Invalid gzip_packed message") from exc
        if end != len(payload):
            raise RpcSenderError("Unexpected trailing bytes in gzip_packed message")
        _validate_nested_message_lengths(unpacked, depth=depth + 1)


@dataclass(slots=True)
class _PendingCall:
    req_bytes: bytes
    future: asyncio.Future[Any]
    msg_ids: set[int] = field(default_factory=set)
    attempts: int = 0
    active_msg_id: int | None = None
    bad_salt_retries: int = 0
    bad_time_retries: int = 0


@dataclass(slots=True)
class FloodWaitConfig:
    """Configuration for automatic FloodWait retry."""

    enabled: bool = True
    max_wait_seconds: int = 60  # Don't auto-wait more than this
    max_retries: int = 3  # Max number of flood wait retries per call

    def __post_init__(self) -> None:
        if self.max_wait_seconds < 0:
            raise ValueError("max_wait_seconds must be >= 0")
        if self.max_retries < 0:
            raise ValueError("max_retries must be >= 0")


class MtprotoEncryptedSender:
    """
    Encrypted MTProto sender with basic RPC request/response mapping.

    - Matches responses using `rpc_result.req_msg_id`.
    - Handles `msg_container` and `gzip_packed` via the TL codec.
    - Sends `msgs_ack` for received messages.
    - Retries once on `bad_server_salt` (updates `server_salt`).
    - Responds to `msg_resend_req` for in-flight requests.
    - Auto-retries on FLOOD_WAIT_X errors (configurable).
    """

    def __init__(
        self,
        transport: PacketTransport,
        *,
        state: MtprotoState,
        msg_id_gen: MsgIdGenerator,
        incoming_queue: asyncio.Queue[
            ReceivedMessage | ReceiverTerminated | UpdatesRecoveryRequired
        ]
        | None = None,
        flood_wait_config: FloodWaitConfig | None = None,
    ) -> None:
        self._transport = transport
        self._state = state
        self._msg_id_gen = msg_id_gen
        self._send_lock = asyncio.Lock()
        self._recv_task: asyncio.Task[None] | None = None
        self._close_lock = asyncio.Lock()
        self._closed_event = asyncio.Event()
        self._pending: dict[int, _PendingCall] = {}
        self._sent: dict[int, tuple[int, bytes]] = {}  # msg_id -> (seqno, body)
        self._closed = False
        self._terminal_error: RpcSenderError | None = None
        self._incoming_queue = incoming_queue
        self._flood_wait_config = flood_wait_config or FloodWaitConfig()
        # MTProto requires a bounded cache of recently accepted server msg_ids
        # to reject duplicates and messages older than the retained receive window.
        self._received_msg_ids: set[int] = set()

    def _forward_incoming(
        self,
        item: ReceivedMessage | ReceiverTerminated | UpdatesRecoveryRequired,
    ) -> None:
        """Forward an update-side event without ever blocking the RPC receiver.

        A full queue means the exact update stream can no longer be preserved in
        memory.  Clearing it and inserting a recovery marker is safe because the
        updates engine will resume from its last persisted pts/qts checkpoint via
        ``updates.getDifference``.  Keeping this operation non-blocking is
        essential: RPC results share the same MTProto receive loop.
        """

        queue = self._incoming_queue
        if queue is None:
            return
        try:
            queue.put_nowait(item)
            return
        except asyncio.QueueFull:
            pass

        dropped = 0
        while True:
            try:
                queue.get_nowait()
                dropped += 1
            except asyncio.QueueEmpty:
                break

        if isinstance(item, ReceiverTerminated) or (
            isinstance(item, UpdatesRecoveryRequired) and item.requires_reconnect
        ):
            replacement: ReceivedMessage | ReceiverTerminated | UpdatesRecoveryRequired = item
        else:
            replacement = UpdatesRecoveryRequired(reason="incoming_queue_overflow")
        queue.put_nowait(replacement)
        if isinstance(replacement, ReceiverTerminated):
            logger.error(
                "MTProto incoming queue overflowed; discarded %d buffered events to expose "
                "the terminal receiver error",
                dropped,
            )
        else:
            logger.error(
                "MTProto incoming update queue overflowed; discarded %d buffered events and "
                "scheduled updates.getDifference recovery",
                dropped,
            )

    @property
    def is_healthy(self) -> bool:
        task = self._recv_task
        return (
            not self._closed and self._terminal_error is None and (task is None or not task.done())
        )

    @property
    def terminal_error(self) -> RpcSenderError | None:
        return self._terminal_error

    def invalidate(self, error: RpcSenderError | None = None) -> RpcSenderError:
        """Synchronously prevent new/retried sends and wake FloodWait sleepers."""

        terminal = self._terminal_error
        if terminal is None:
            terminal = error or RpcSenderError("Sender is closed")
            self._terminal_error = terminal
        self._closed = True
        self._closed_event.set()
        self._fail_all_pending(terminal)
        return terminal

    async def close(self) -> None:
        async with self._close_lock:
            self.invalidate(RpcSenderError("Sender is closed"))
            task = self._recv_task
            if task is not None:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                self._recv_task = None
            # Do not wait for the send lock here. A blocked transport.send() is
            # released by MtprotoClient closing the transport immediately after
            # this method returns; waiting for that same send would deadlock close.

    def _raise_if_unavailable(self) -> None:
        if self._terminal_error is not None:
            raise self._terminal_error
        if self._closed:
            raise RpcSenderError("Sender is closed")

    def _ensure_recv_task(self) -> None:
        self._raise_if_unavailable()
        if self._recv_task is None:
            self._recv_task = asyncio.create_task(self._recv_loop())
        elif self._recv_task.done():
            error = RpcSenderError("Receiver loop stopped unexpectedly")
            self.invalidate(error)
            raise error

    async def invoke_tl(
        self,
        req_obj: Any,
        *,
        timeout: float = 20.0,
        flood_wait_config: FloodWaitConfig | None = None,
    ) -> Any:
        """
        Send a TLRequest-like object (serialized via telecraft.tl.codec.dumps) and return result.

        Automatically handles FLOOD_WAIT_X errors by sleeping and retrying (configurable).
        """

        from telecraft.tl.codec import dumps

        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be a positive finite number")

        self._ensure_recv_task()

        fw_config = flood_wait_config or self._flood_wait_config
        flood_retries = 0
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout

        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise RpcSenderError(f"Timed out waiting for response (total deadline={timeout}s)")
            try:
                # Cover serialization/send-lock/transport.send as well as the
                # response wait.  The timeout is a total call deadline, not a
                # fresh allowance for every FloodWait retry.
                result = await asyncio.wait_for(
                    self._invoke_tl_once(req_obj, dumps_fn=dumps, timeout=remaining),
                    timeout=remaining,
                )
            except asyncio.TimeoutError as exc:
                raise RpcSenderError(
                    f"Timed out waiting for response (total deadline={timeout}s)"
                ) from exc

            # Check if this is a FloodWaitError that we should auto-handle
            if isinstance(result, FloodWaitError):
                wait_secs = result.wait_seconds

                if not fw_config.enabled:
                    raise result

                if flood_retries >= fw_config.max_retries:
                    logger.warning(
                        "FloodWait: max retries (%d) reached; raising error",
                        fw_config.max_retries,
                    )
                    raise result

                if wait_secs > fw_config.max_wait_seconds:
                    logger.warning(
                        "FloodWait: wait time (%ds) exceeds max (%ds); raising error",
                        wait_secs,
                        fw_config.max_wait_seconds,
                    )
                    raise result

                remaining = deadline - loop.time()
                if wait_secs >= remaining:
                    logger.warning(
                        "FloodWait: wait time (%ds) exceeds remaining call deadline (%.3fs); "
                        "raising error",
                        wait_secs,
                        max(0.0, remaining),
                    )
                    raise result

                flood_retries += 1
                logger.info(
                    "FloodWait: sleeping %ds before retry %d/%d",
                    wait_secs,
                    flood_retries,
                    fw_config.max_retries,
                )
                try:
                    await asyncio.wait_for(
                        self._closed_event.wait(),
                        timeout=float(wait_secs),
                    )
                except asyncio.TimeoutError:
                    pass
                else:
                    self._raise_if_unavailable()
                continue

            return result

    async def _invoke_tl_once(
        self,
        req_obj: Any,
        *,
        dumps_fn: Any,
        timeout: float,
    ) -> Any:
        """
        Internal: single invoke attempt. Returns result or FloodWaitError.
        """
        req_bytes = dumps_fn(req_obj)
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[Any] = loop.create_future()
        call = _PendingCall(req_bytes=req_bytes, future=fut)

        try:
            await self._send_new_attempt(call)
            try:
                # A timeout does not prove that Telegram failed to execute the
                # request. Blindly resending a non-idempotent RPC with a fresh
                # msg_id can execute it twice; safe retry needs msgs_state_req
                # or a protocol-level container strategy.
                result = await asyncio.wait_for(fut, timeout=timeout)
            except asyncio.TimeoutError as e:
                self._cleanup_call(call)
                raise RpcSenderError(f"Timed out waiting for response (timeout={timeout}s)") from e
            except FloodWaitError:
                # Return FloodWaitError for handling by invoke_tl
                self._cleanup_call(call)
                raise
            except Exception:
                self._cleanup_call(call)
                raise
            else:
                self._cleanup_call(call)
                return result
        except FloodWaitError as e:
            # Return error for outer loop to handle
            return e
        except asyncio.CancelledError:
            if not fut.done():
                fut.cancel()
            self._cleanup_call(call)
            raise
        except Exception:
            if not fut.done():
                fut.cancel()
            self._cleanup_call(call)
            raise

    async def _send_new_attempt(self, call: _PendingCall) -> int:
        self._raise_if_unavailable()
        msg_id = self._msg_id_gen.next()
        seqno = self._state.next_seq_no(content_related=True)
        inner = struct.pack("<qii", msg_id, seqno, len(call.req_bytes)) + call.req_bytes
        packet = self._state.encrypt_inner_message(inner, to_server=True)
        async with self._send_lock:
            self._raise_if_unavailable()
            # Register before the await: a loopback or very fast server response
            # may be processed while transport.send() is still yielding.
            call.attempts += 1
            call.msg_ids.add(msg_id)
            previous_active_msg_id = call.active_msg_id
            call.active_msg_id = msg_id
            self._pending[msg_id] = call
            self._sent[msg_id] = (seqno, call.req_bytes)
            try:
                await self._transport.send(packet)
                self._raise_if_unavailable()
            except BaseException:
                if self._pending.get(msg_id) is call:
                    self._pending.pop(msg_id, None)
                self._sent.pop(msg_id, None)
                call.msg_ids.discard(msg_id)
                call.active_msg_id = previous_active_msg_id
                raise
        return msg_id

    async def _send_inner_message(self, *, msg_id: int, seqno: int, body: bytes) -> None:
        inner = struct.pack("<qii", msg_id, seqno, len(body)) + body
        packet = self._state.encrypt_inner_message(inner, to_server=True)
        async with self._send_lock:
            await self._transport.send(packet)

    async def _send_ack(self, msg_ids: list[int]) -> None:
        if not msg_ids:
            return
        # De-duplicate while keeping deterministic order.
        uniq: list[int] = []
        seen: set[int] = set()
        for mid in msg_ids:
            if mid in seen:
                continue
            seen.add(mid)
            uniq.append(mid)

        ack = MsgsAck(msg_ids=uniq)
        from telecraft.tl.codec import dumps

        body = dumps(ack)
        msg_id = self._msg_id_gen.next()
        seqno = self._state.next_seq_no(content_related=False)
        await self._send_inner_message(msg_id=msg_id, seqno=seqno, body=body)

    def _cleanup_call(self, call: _PendingCall) -> None:
        for mid in list(call.msg_ids):
            if self._pending.get(mid) is call:
                self._pending.pop(mid, None)
            self._sent.pop(mid, None)

    def _fail_all_pending(self, error: RpcSenderError) -> None:
        calls = {id(call): call for call in self._pending.values()}.values()
        for call in calls:
            if not call.future.done():
                call.future.set_exception(error)
        self._pending.clear()
        self._sent.clear()

    def _poison_for_decode_failure(
        self,
        error: Exception,
        *,
        outer_msg_id: int | None,
        default_path: str = "root",
    ) -> RpcDecodeError:
        """Make an undecodable connection terminal without acknowledging its payload.

        An unknown nested object or trailing data at a bounded object boundary
        means the envelope cannot be classified safely. Telegram's recovery
        contract requires a fresh TCP/session/layer handshake before fetching the
        difference; acknowledging it could make a lost update look committed.
        """

        decode_error = RpcDecodeError.from_decode_failure(
            error,
            outer_msg_id=outer_msg_id,
            default_path=default_path,
        )
        self.invalidate(decode_error)
        if self._incoming_queue is not None:
            self._forward_incoming(ReceiverTerminated(error=decode_error))
        return decode_error

    def _fail_decode_for_req_ids(
        self,
        *,
        req_msg_ids: set[int],
        outer_msg_id: int,
        error: Exception,
    ) -> None:
        if not req_msg_ids:
            logger.warning(
                "TL decode failed for msg_id=%s but no req_msg_id could be extracted: %s",
                outer_msg_id,
                error,
            )
            return

        affected: dict[int, tuple[int, _PendingCall]] = {}
        for req_msg_id in req_msg_ids:
            call = self._pending.get(req_msg_id)
            if call is None or call.future.done():
                continue
            affected[id(call)] = (req_msg_id, call)

        if not affected:
            logger.warning(
                "TL decode failed for msg_id=%s (req_ids=%s) but no active pending call matched",
                outer_msg_id,
                sorted(req_msg_ids),
            )
            return

        for req_msg_id, call in affected.values():
            call.future.set_exception(
                RpcDecodeError(
                    f"Failed to decode response for req_msg_id={req_msg_id} "
                    f"(outer_msg_id={outer_msg_id}): {error}"
                )
            )

    def _server_msg_id_rejection_reason(
        self,
        msg_id: int,
        *,
        now: int,
        floor: int | None,
    ) -> str | None:
        """Return why a server msg_id must be ignored, or ``None`` when valid."""

        if msg_id <= 0:
            return "non-positive"
        if msg_id & 1 == 0:
            return "invalid server parity"

        msg_time = msg_id >> 32
        if msg_time > now + _SERVER_MSG_ID_MAX_FUTURE_SECONDS:
            return "more than 30 seconds in the future"
        if msg_time < now - _SERVER_MSG_ID_MAX_PAST_SECONDS:
            return "more than 300 seconds in the past"
        if msg_id in self._received_msg_ids:
            return "duplicate"
        if floor is not None and msg_id < floor:
            return "older than the retained receive window"
        return None

    def _accept_server_msg_ids(
        self,
        msg_ids: list[int],
        *,
        now: int | None = None,
    ) -> set[int]:
        """Validate and remember a batch of incoming server message identifiers.

        A container's outer id is normally newer than its inner ids.  The whole
        batch is therefore checked against one pre-batch cache snapshot before any
        accepted id is inserted.
        """

        now_seconds = int(time.time()) if now is None else int(now)
        floor = min(self._received_msg_ids) if self._received_msg_ids else None
        accepted: set[int] = set()
        seen_in_batch: set[int] = set()

        for raw_msg_id in msg_ids:
            msg_id = int(raw_msg_id)
            if msg_id in seen_in_batch:
                logger.debug("Ignoring duplicate server msg_id=%s within one packet", msg_id)
                continue
            seen_in_batch.add(msg_id)

            reason = self._server_msg_id_rejection_reason(
                msg_id,
                now=now_seconds,
                floor=floor,
            )
            if reason is not None:
                quietly_ignored = {
                    "duplicate",
                    "older than the retained receive window",
                }
                log = logger.debug if reason in quietly_ignored else logger.warning
                log("Ignoring server msg_id=%s: %s", msg_id, reason)
                continue
            accepted.add(msg_id)

        self._received_msg_ids.update(accepted)
        excess = len(self._received_msg_ids) - _RECEIVED_MSG_ID_CACHE_SIZE
        if excess > 0:
            for msg_id in sorted(self._received_msg_ids)[:excess]:
                self._received_msg_ids.discard(msg_id)
        return accepted

    @staticmethod
    def _collect_received_msg_ids(
        obj: Any,
        *,
        outer_msg_id: int,
    ) -> tuple[list[int], set[int]]:
        """Collect outer/inner ids and identify container envelopes, which are not leaves."""

        msg_ids = [int(outer_msg_id)]
        container_msg_ids: set[int] = set()

        def walk(current: Any, *, current_msg_id: int) -> None:
            if not isinstance(current, MsgContainer):
                return
            container_msg_ids.add(current_msg_id)
            for message in current.messages:
                nested_msg_id = int(message.msg_id)
                msg_ids.append(nested_msg_id)
                walk(message.obj, current_msg_id=nested_msg_id)

        walk(obj, current_msg_id=int(outer_msg_id))
        return msg_ids, container_msg_ids

    def _unwrap_received(self, obj: Any, *, msg_id: int, seqno: int) -> list[ReceivedMessage]:
        # Note: We intentionally do NOT unwrap RpcResult here; we need req_msg_id.
        if isinstance(obj, MsgContainer):
            out: list[ReceivedMessage] = []
            for m in obj.messages:
                out.extend(self._unwrap_received(m.obj, msg_id=int(m.msg_id), seqno=int(m.seqno)))
            return out
        return [ReceivedMessage(msg_id=msg_id, seqno=seqno, obj=obj)]

    def _matching_active_call(
        self,
        *,
        bad_msg_id: int,
        bad_seqno: int,
    ) -> _PendingCall | None:
        call = self._pending.get(int(bad_msg_id))
        sent = self._sent.get(int(bad_msg_id))
        if (
            call is None
            or call.future.done()
            or call.active_msg_id != int(bad_msg_id)
            or bad_msg_id not in call.msg_ids
            or sent is None
        ):
            return None
        if int(bad_seqno) != int(sent[0]):
            logger.warning(
                "Ignoring bad-message recovery with mismatched seqno "
                "bad_msg_id=%s expected=%s got=%s",
                bad_msg_id,
                sent[0],
                bad_seqno,
            )
            return None
        return call

    def _validated_time_recovery_ids(
        self,
        obj: Any,
        *,
        outer_msg_id: int,
        outer_seqno: int,
    ) -> set[int]:
        """Return server IDs carrying a validated time/salt recovery notification."""

        correction_ids: set[int] = set()
        for message in self._unwrap_received(
            obj,
            msg_id=int(outer_msg_id),
            seqno=int(outer_seqno),
        ):
            notification = message.obj
            if isinstance(notification, BadMsgNotification):
                if int(cast(int, notification.error_code)) not in {16, 17}:
                    continue
            elif isinstance(notification, BadServerSalt):
                if int(cast(int, notification.error_code)) != 48:
                    continue
            else:
                continue

            bad_msg_id = int(cast(int, notification.bad_msg_id))
            bad_seqno = int(cast(int, notification.bad_msg_seqno))
            if (
                self._matching_active_call(
                    bad_msg_id=bad_msg_id,
                    bad_seqno=bad_seqno,
                )
                is None
            ):
                continue
            correction_ids.add(int(message.msg_id))
        return correction_ids

    async def _handle_message(
        self,
        msg: ReceivedMessage,
        *,
        clock_already_synchronized: bool = False,
    ) -> None:
        obj = msg.obj

        # Some MTProto "service" methods (notably `ping`) may be answered directly,
        # without an `rpc_result` wrapper. In that case, the response includes the
        # original request msg_id as a field.
        if isinstance(obj, Pong):
            req_msg_id = int(cast(int, obj.msg_id))
            call = self._pending.get(req_msg_id)
            if call is None:
                logger.debug("Orphan pong for req msg_id=%s (no pending call)", req_msg_id)
                return
            if not call.future.done():
                call.future.set_result(obj)
            return

        if isinstance(obj, RpcResult):
            req_msg_id = int(obj.req_msg_id)
            result = obj.result
            call = self._pending.get(req_msg_id)
            if call is None:
                logger.debug("Orphan rpc_result for req_msg_id=%s (no pending call)", req_msg_id)
                return
            if call.future.done():
                return

            if isinstance(result, RpcError):
                raw_msg = result.error_message
                if isinstance(raw_msg, (bytes, bytearray)):
                    message = bytes(raw_msg).decode("utf-8", "replace")
                else:
                    message = str(raw_msg)
                code = int(cast(int, result.error_code))

                # Check for FloodWait-type errors
                wait_seconds = parse_flood_wait_seconds(message)
                if wait_seconds is not None:
                    call.future.set_exception(
                        FloodWaitError(code=code, message=message, wait_seconds=wait_seconds)
                    )
                elif migrate_match := _MIGRATE_PATTERN.fullmatch(message):
                    call.future.set_exception(
                        DcMigrateError(
                            code=code,
                            message=message,
                            kind=migrate_match.group(1),
                            dc_id=int(migrate_match.group(2)),
                        )
                    )
                else:
                    call.future.set_exception(RpcErrorException(code=code, message=message))
            else:
                call.future.set_result(result)
            return

        if isinstance(obj, NewSessionCreated):
            salt_i64 = cast(int, obj.server_salt)
            self._state.server_salt = _i64_to_le_bytes(int(salt_i64))
            logger.info(
                "NewSessionCreated received; updated server_salt and requesting updates recovery"
            )
            if self._incoming_queue is not None:
                self._forward_incoming(UpdatesRecoveryRequired(reason="new_session_created"))
            return

        if isinstance(obj, BadServerSalt):
            bad_msg_id = int(cast(int, obj.bad_msg_id))
            bad_seqno = int(cast(int, obj.bad_msg_seqno))
            call = self._matching_active_call(
                bad_msg_id=bad_msg_id,
                bad_seqno=bad_seqno,
            )
            if call is None:
                logger.warning(
                    "Ignoring BadServerSalt for unknown, stale, or mismatched msg_id=%s",
                    bad_msg_id,
                )
                return

            new_salt_i64 = cast(int, obj.new_server_salt)
            self._state.server_salt = _i64_to_le_bytes(int(new_salt_i64))

            if call.bad_salt_retries >= 1:
                call.future.set_exception(RpcSenderError("Too many retries after BadServerSalt"))
                return

            call.bad_salt_retries += 1
            logger.warning("BadServerSalt received; updating salt and retrying once")
            await self._send_new_attempt(call)
            return

        if isinstance(obj, BadMsgNotification):
            bad_msg_id = int(cast(int, obj.bad_msg_id))
            bad_seqno = int(cast(int, obj.bad_msg_seqno))
            call = self._matching_active_call(
                bad_msg_id=bad_msg_id,
                bad_seqno=bad_seqno,
            )
            if call is None:
                logger.warning(
                    "Ignoring BadMsgNotification for unknown, stale, or mismatched "
                    "msg_id=%s (error_code=%s)",
                    bad_msg_id,
                    int(cast(int, obj.error_code)),
                )
                return
            error_code = int(cast(int, obj.error_code))
            if error_code in {16, 17}:
                if call.bad_time_retries >= 1:
                    call.future.set_exception(
                        RpcSenderError("Too many retries after bad msg_id time correction")
                    )
                    return
                if not clock_already_synchronized:
                    self._msg_id_gen.synchronize_from_msg_id(msg.msg_id)
                    # synchronize_from_msg_id resets the rejected client floor.
                    # Re-observe the valid server notification so the retry is
                    # still newer than the message that authorized correction.
                    self._msg_id_gen.observe(msg.msg_id)
                call.bad_time_retries += 1
                logger.warning(
                    "BadMsgNotification error_code=%s; correcting clock and retrying once",
                    error_code,
                )
                await self._send_new_attempt(call)
                return
            call.future.set_exception(RpcSenderError(f"BadMsgNotification error_code={error_code}"))
            return

        if isinstance(obj, MsgResendReq):
            msg_ids = cast(list[int], obj.msg_ids)
            for mid in msg_ids:
                mid_i = int(mid)
                if mid_i not in self._sent:
                    continue
                seqno, body = self._sent[mid_i]
                logger.debug("Resending requested message msg_id=%s", mid_i)
                await self._send_inner_message(msg_id=mid_i, seqno=seqno, body=body)
            return

        # Other service / update messages are ignored for now.
        if self._is_ignorable(obj):
            return
        if self._incoming_queue is not None:
            self._forward_incoming(msg)
        else:
            logger.debug("Unhandled message: %s", getattr(obj, "TL_NAME", type(obj).__name__))

    async def _recv_loop(self) -> None:
        try:
            while True:
                packet = await self._transport.recv()
                # decrypt_packet validates auth_key_id/msg_key before returning.
                # Failures here have not crossed the authenticated TL boundary and
                # intentionally remain terminal crypto/transport errors in the
                # outer handler, rather than being mislabeled RpcDecodeError.
                inner_resp = self._state.decrypt_packet(packet, from_server=True)
                try:
                    outer_msg_id, outer_seqno, body = _parse_inner_message(inner_resp)
                except RpcSenderError as e:
                    decode_error = self._poison_for_decode_failure(
                        e,
                        outer_msg_id=None,
                        default_path="mtproto.inner_message",
                    )
                    logger.error(
                        "Malformed authenticated MTProto inner message poisoned the connection; "
                        "the envelope was not acknowledged and all pending calls failed",
                        exc_info=decode_error,
                    )
                    return

                now = int(self._msg_id_gen.now())
                floor = min(self._received_msg_ids) if self._received_msg_ids else None
                reason = self._server_msg_id_rejection_reason(
                    outer_msg_id,
                    now=now,
                    floor=floor,
                )
                time_rejection = reason in {
                    "more than 30 seconds in the future",
                    "more than 300 seconds in the past",
                }
                if reason is not None and not time_rejection:
                    logger.debug(
                        "Ignoring incoming packet with server msg_id=%s: %s",
                        outer_msg_id,
                        reason,
                    )
                    continue

                try:
                    _validate_nested_message_lengths(body)
                    obj = loads(body)
                except (TLCodecError, RpcSenderError) as e:
                    decode_error = self._poison_for_decode_failure(
                        e,
                        outer_msg_id=outer_msg_id,
                    )
                    constructor_id = getattr(e, "constructor_id", None)
                    logger.error(
                        "Undecodable authenticated TL payload poisoned the MTProto connection; "
                        "the payload was not acknowledged and all pending calls failed "
                        "(failure=%s, path=%s, outer_msg_id=%s)",
                        (
                            f"0x{constructor_id & 0xFFFFFFFF:08x}"
                            if isinstance(constructor_id, int)
                            else "trailing-data"
                        ),
                        getattr(e, "path", None),
                        outer_msg_id,
                        exc_info=decode_error,
                    )
                    return

                clock_correction_ids: set[int] = set()
                if time_rejection:
                    # A cryptographically valid bad_msg_notification is the
                    # recovery mechanism for a client clock outside the normal
                    # receive window. Telegram additionally requires that it
                    # refer to a recently sent message before adjusting time.
                    clock_correction_ids = self._validated_time_recovery_ids(
                        obj,
                        outer_msg_id=outer_msg_id,
                        outer_seqno=outer_seqno,
                    )
                    if not clock_correction_ids:
                        logger.warning(
                            "Ignoring time-skewed server msg_id=%s without a valid "
                            "pending-call clock correction",
                            outer_msg_id,
                        )
                        continue
                    self._msg_id_gen.synchronize_from_msg_id(max(clock_correction_ids))
                    now = int(self._msg_id_gen.now())

                candidate_ids, container_msg_ids = self._collect_received_msg_ids(
                    obj,
                    outer_msg_id=outer_msg_id,
                )
                accepted_ids = self._accept_server_msg_ids(candidate_ids, now=now)
                if outer_msg_id not in accepted_ids:
                    continue
                for msg_id in accepted_ids:
                    self._msg_id_gen.observe(msg_id)

                received = self._unwrap_received(obj, msg_id=outer_msg_id, seqno=outer_seqno)

                ack_ids: list[int] = []
                processed_ids = set(container_msg_ids)
                for m in received:
                    if m.msg_id not in accepted_ids or m.msg_id in processed_ids:
                        continue
                    processed_ids.add(m.msg_id)
                    if not isinstance(m.obj, MsgsAck):
                        ack_ids.append(m.msg_id)
                    await self._handle_message(
                        m,
                        clock_already_synchronized=m.msg_id in clock_correction_ids,
                    )

                await self._send_ack(ack_ids)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("Receiver loop crashed; failing all pending calls")
            error = RpcSenderError(f"Receiver loop crashed ({type(exc).__name__}: {exc})")
            error.__cause__ = exc
            self.invalidate(error)
            if self._incoming_queue is not None:
                self._forward_incoming(ReceiverTerminated(error=error))

    def _is_ignorable(self, obj: Any) -> bool:
        name = getattr(obj, "TL_NAME", None)
        if not isinstance(name, str):
            return False
        return name in {
            "msgs_ack",
            "msgs_state_req",
            "msgs_state_info",
            "msgs_all_info",
            "msg_detailed_info",
            "msg_new_detailed_info",
            "new_session_created",
        }
