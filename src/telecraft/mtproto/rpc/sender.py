from __future__ import annotations

import asyncio
import logging
import struct
from dataclasses import dataclass
from typing import Any, Protocol, cast

from telecraft.mtproto.core.msg_id import MsgIdGenerator
from telecraft.mtproto.core.state import MtprotoState
from telecraft.tl.codec import MsgContainer, RpcResult, loads
from telecraft.tl.generated.types import BadServerSalt, NewSessionCreated

logger = logging.getLogger(__name__)


class PacketTransport(Protocol):
    async def send(self, payload: bytes) -> None: ...
    async def recv(self) -> bytes: ...


class RpcSenderError(Exception):
    pass


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


class MtprotoEncryptedSender:
    """
    Minimal encrypted sender: send one request, wait for one response.

    This intentionally does not implement a full request queue, acks/resends, etc.
    It's enough to validate MTProto v2 encryption and start building higher layers.
    """

    def __init__(
        self,
        transport: PacketTransport,
        *,
        state: MtprotoState,
        msg_id_gen: MsgIdGenerator,
    ) -> None:
        self._transport = transport
        self._state = state
        self._msg_id_gen = msg_id_gen

    async def invoke_tl(self, req_obj: Any, *, timeout: float = 20.0) -> Any:
        """
        Send a TLRequest-like object (serialized via telecraft.tl.codec.dumps) and return result.
        """

        from telecraft.tl.codec import dumps

        req_bytes = dumps(req_obj)

        for attempt in range(2):
            msg_id = self._msg_id_gen.next()
            seqno = self._state.next_seq_no(content_related=True)
            inner = struct.pack("<qii", msg_id, seqno, len(req_bytes)) + req_bytes
            packet = self._state.encrypt_inner_message(inner)
            await self._transport.send(packet)

            deadline = asyncio.get_running_loop().time() + timeout
            while True:
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    raise RpcSenderError(
                        f"Timed out waiting for response (timeout={timeout}s)"
                    )
                try:
                    resp_packet = await asyncio.wait_for(self._transport.recv(), timeout=remaining)
                except TimeoutError as e:
                    raise RpcSenderError(
                        f"Timed out waiting for response (timeout={timeout}s)"
                    ) from e

                inner_resp = self._state.decrypt_packet(resp_packet)
                remote_msg_id, _remote_seqno, body = _parse_inner_message(inner_resp)
                self._msg_id_gen.observe(remote_msg_id)

                obj = loads(body)

                # Unwrap containers/rpc_result (may yield multiple objects).
                received_list = self._flatten(obj)

                # Process all received objects. Some packets (first encrypted response)
                # may contain only service messages like `new_session_created`.
                need_retry = False
                for received in received_list:
                    if received is None:
                        continue

                    if isinstance(received, BadServerSalt) and attempt == 0:
                        new_salt_i64 = cast(int, received.new_server_salt)
                        new_salt = _i64_to_le_bytes(int(new_salt_i64))
                        logger.warning("BadServerSalt received; updating salt and retrying once")
                        self._state.server_salt = new_salt
                        need_retry = True
                        break  # break received_list loop -> retry outer attempt

                    if isinstance(received, NewSessionCreated):
                        salt_i64 = cast(int, received.server_salt)
                        self._state.server_salt = _i64_to_le_bytes(int(salt_i64))
                        logger.debug("NewSessionCreated received; updated server_salt")
                        continue

                    if self._is_ignorable(received):
                        continue

                    return received

                else:
                    # No meaningful response in this packet; keep receiving.
                    continue

                if need_retry:
                    break

            # outer retry loop continues

        raise RpcSenderError("Too many retries")

    def _flatten(self, obj: Any) -> list[Any]:
        """
        Flatten rpc_result and msg_container into a list of underlying objects.
        """

        if isinstance(obj, RpcResult):
            return self._flatten(obj.result)
        if isinstance(obj, MsgContainer):
            out: list[Any] = []
            for m in obj.messages:
                out.extend(self._flatten(m.obj))
            return out
        return [obj]

    def _is_ignorable(self, obj: Any) -> bool:
        name = getattr(obj, "TL_NAME", None)
        if not isinstance(name, str):
            return False
        return name in {
            "msgs_ack",
            "msgs_state_req",
            "msgs_state_info",
            "msg_detailed_info",
            "msg_new_detailed_info",
            "new_session_created",
        }

