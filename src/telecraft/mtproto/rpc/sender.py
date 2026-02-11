from __future__ import annotations

import asyncio
import logging
import re
import struct
from dataclasses import dataclass, field
from typing import Any, Protocol, cast

from telecraft.mtproto.core.msg_id import MsgIdGenerator
from telecraft.mtproto.core.state import MtprotoState
from telecraft.tl.codec import MsgContainer, RpcResult, loads
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


def _parse_inner_message(inner: bytes) -> tuple[int, int, bytes]:
    if len(inner) < 16:
        raise RpcSenderError("Inner message too short")
    msg_id = struct.unpack_from("<q", inner, 0)[0]
    seqno = struct.unpack_from("<i", inner, 8)[0]
    msg_len = struct.unpack_from("<i", inner, 12)[0]
    if msg_len < 0:
        raise RpcSenderError("Negative message length")
    end = 16 + msg_len
    if end > len(inner):
        raise RpcSenderError("Message length exceeds decrypted payload")
    return msg_id, seqno, inner[16:end]


def _i64_to_le_bytes(x: int) -> bytes:
    return (int(x) & ((1 << 64) - 1)).to_bytes(8, "little", signed=False)


@dataclass(slots=True)
class _PendingCall:
    req_bytes: bytes
    future: asyncio.Future[Any]
    msg_ids: set[int] = field(default_factory=set)
    attempts: int = 0


@dataclass(slots=True)
class FloodWaitConfig:
    """Configuration for automatic FloodWait retry."""

    enabled: bool = True
    max_wait_seconds: int = 60  # Don't auto-wait more than this
    max_retries: int = 3  # Max number of flood wait retries per call


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
        incoming_queue: asyncio.Queue[ReceivedMessage] | None = None,
        flood_wait_config: FloodWaitConfig | None = None,
    ) -> None:
        self._transport = transport
        self._state = state
        self._msg_id_gen = msg_id_gen
        self._send_lock = asyncio.Lock()
        self._recv_task: asyncio.Task[None] | None = None
        self._pending: dict[int, _PendingCall] = {}
        self._sent: dict[int, tuple[int, bytes]] = {}  # msg_id -> (seqno, body)
        self._closed = False
        self._incoming_queue = incoming_queue
        self._flood_wait_config = flood_wait_config or FloodWaitConfig()

    async def close(self) -> None:
        self._closed = True
        if self._recv_task is not None:
            self._recv_task.cancel()
            try:
                await self._recv_task
            except asyncio.CancelledError:
                pass
            self._recv_task = None

    def _ensure_recv_task(self) -> None:
        if self._recv_task is None:
            self._recv_task = asyncio.create_task(self._recv_loop())

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

        if self._closed:
            raise RpcSenderError("Sender is closed")

        self._ensure_recv_task()

        fw_config = flood_wait_config or self._flood_wait_config
        flood_retries = 0

        while True:
            result = await self._invoke_tl_once(req_obj, dumps_fn=dumps, timeout=timeout)

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

                flood_retries += 1
                logger.info(
                    "FloodWait: sleeping %ds before retry %d/%d",
                    wait_secs,
                    flood_retries,
                    fw_config.max_retries,
                )
                await asyncio.sleep(wait_secs)
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

            for attempt in range(2):
                try:
                    result = await asyncio.wait_for(fut, timeout=timeout)
                except TimeoutError as e:
                    if attempt == 0 and not fut.done():
                        logger.warning("Timed out waiting for RPC result; retrying once")
                        await self._send_new_attempt(call)
                        continue
                    if not fut.done():
                        fut.cancel()
                    self._cleanup_call(call)
                    raise RpcSenderError(
                        f"Timed out waiting for response (timeout={timeout}s)"
                    ) from e
                except FloodWaitError:
                    # Return FloodWaitError for handling by invoke_tl
                    self._cleanup_call(call)
                    raise
                else:
                    self._cleanup_call(call)
                    return result

            self._cleanup_call(call)
            raise RpcSenderError("Too many retries")
        except FloodWaitError as e:
            # Return error for outer loop to handle
            return e
        except asyncio.CancelledError:
            if not fut.done():
                fut.cancel()
            self._cleanup_call(call)
            raise

    async def _send_new_attempt(self, call: _PendingCall) -> int:
        msg_id = self._msg_id_gen.next()
        seqno = self._state.next_seq_no(content_related=True)
        await self._send_inner_message(msg_id=msg_id, seqno=seqno, body=call.req_bytes)

        call.attempts += 1
        call.msg_ids.add(msg_id)
        self._pending[msg_id] = call
        self._sent[msg_id] = (seqno, call.req_bytes)
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

    def _unwrap_received(self, obj: Any, *, msg_id: int, seqno: int) -> list[ReceivedMessage]:
        # Note: We intentionally do NOT unwrap RpcResult here; we need req_msg_id.
        if isinstance(obj, MsgContainer):
            out: list[ReceivedMessage] = []
            for m in obj.messages:
                out.extend(self._unwrap_received(m.obj, msg_id=int(m.msg_id), seqno=int(m.seqno)))
            return out
        return [ReceivedMessage(msg_id=msg_id, seqno=seqno, obj=obj)]

    async def _handle_message(self, msg: ReceivedMessage) -> None:
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
                else:
                    call.future.set_exception(RpcErrorException(code=code, message=message))
            else:
                call.future.set_result(result)
            return

        if isinstance(obj, NewSessionCreated):
            salt_i64 = cast(int, obj.server_salt)
            self._state.server_salt = _i64_to_le_bytes(int(salt_i64))
            logger.debug("NewSessionCreated received; updated server_salt")
            return

        if isinstance(obj, BadServerSalt):
            new_salt_i64 = cast(int, obj.new_server_salt)
            self._state.server_salt = _i64_to_le_bytes(int(new_salt_i64))

            bad_msg_id = int(cast(int, obj.bad_msg_id))
            call = self._pending.get(bad_msg_id)
            if call is None:
                logger.warning("BadServerSalt for unknown msg_id=%s; updated salt only", bad_msg_id)
                return

            if call.future.done():
                return

            if call.attempts >= 2:
                call.future.set_exception(RpcSenderError("Too many retries after BadServerSalt"))
                return

            logger.warning("BadServerSalt received; updating salt and retrying once")
            await self._send_new_attempt(call)
            return

        if isinstance(obj, BadMsgNotification):
            bad_msg_id = int(cast(int, obj.bad_msg_id))
            call = self._pending.get(bad_msg_id)
            if call is None:
                logger.warning(
                    "BadMsgNotification for unknown msg_id=%s (error_code=%s)",
                    bad_msg_id,
                    int(cast(int, obj.error_code)),
                )
                return
            if not call.future.done():
                call.future.set_exception(
                    RpcSenderError(
                        f"BadMsgNotification error_code={int(cast(int, obj.error_code))}"
                    )
                )
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
            try:
                self._incoming_queue.put_nowait(msg)
            except asyncio.QueueFull:
                name = getattr(obj, "TL_NAME", type(obj).__name__)
                logger.warning("Incoming queue full; dropping message %s", name)
                return
        else:
            logger.debug("Unhandled message: %s", getattr(obj, "TL_NAME", type(obj).__name__))

    async def _recv_loop(self) -> None:
        try:
            while True:
                packet = await self._transport.recv()
                inner_resp = self._state.decrypt_packet(packet, from_server=True)
                outer_msg_id, outer_seqno, body = _parse_inner_message(inner_resp)

                # Robust msg id generator: observe server time progression.
                self._msg_id_gen.observe(outer_msg_id)

                obj = loads(body)
                received = self._unwrap_received(obj, msg_id=outer_msg_id, seqno=outer_seqno)

                ack_ids: list[int] = []
                for m in received:
                    self._msg_id_gen.observe(m.msg_id)
                    if not isinstance(m.obj, MsgsAck):
                        ack_ids.append(m.msg_id)
                    await self._handle_message(m)

                await self._send_ack(ack_ids)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("Receiver loop crashed; failing all pending calls")
            for call in {id(c): c for c in self._pending.values()}.values():
                if not call.future.done():
                    call.future.set_exception(RpcSenderError("Receiver loop crashed"))
            self._pending.clear()
            self._sent.clear()

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
