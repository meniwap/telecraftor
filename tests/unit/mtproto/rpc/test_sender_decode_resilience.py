from __future__ import annotations

import asyncio
import contextlib
import gzip
import struct
import time
from dataclasses import dataclass

import pytest

from telecraft.mtproto.core.msg_id import MsgIdGenerator
from telecraft.mtproto.core.state import MtprotoStateError
from telecraft.mtproto.gzip_utils import MAX_GZIP_UNPACKED_SIZE
from telecraft.mtproto.rpc.sender import (
    MtprotoEncryptedSender,
    ReceivedMessage,
    ReceiverTerminated,
    RpcDecodeError,
    RpcSenderError,
    TLCodecError,
    UpdatesRecoveryRequired,
    _PendingCall,
    _validate_nested_message_lengths,
    extract_req_msg_ids_from_payload,
)
from telecraft.tl.codec import TLWriter, dumps
from telecraft.tl.generated.types import (
    BadMsgNotification,
    BadServerSalt,
    MessageMediaPoll,
    Poll,
    Pong,
    TextWithEntities,
    UpdateConfig,
)

_RPC_RESULT_CONSTRUCTOR_ID = -212046591
_MSG_CONTAINER_CONSTRUCTOR_ID = 1945237724
_GZIP_PACKED_CONSTRUCTOR_ID = 812830625


@dataclass
class _FakeState:
    server_salt: bytes = b"\x00" * 8

    def decrypt_packet(self, packet: bytes, *, from_server: bool) -> bytes:
        return packet

    def encrypt_inner_message(self, inner: bytes, *, to_server: bool) -> bytes:
        return inner

    def next_seq_no(self, *, content_related: bool) -> int:
        return 0


class _FakeMsgIdGen:
    def __init__(self) -> None:
        self._next = 9000
        self.observed: list[int] = []
        self.synchronized: list[int] = []
        self._now = time.time()

    def next(self) -> int:
        self._next += 4
        return self._next

    def observe(self, msg_id: int) -> None:
        self.observed.append(int(msg_id))

    def now(self) -> float:
        return self._now

    def synchronize_from_msg_id(
        self,
        server_msg_id: int,
        *,
        reset_last: bool = True,
    ) -> None:
        _ = reset_last
        self.synchronized.append(int(server_msg_id))
        self._now = float(int(server_msg_id) >> 32)


class _FakeTransport:
    def __init__(self, packets: list[bytes] | None = None) -> None:
        self._queue: asyncio.Queue[bytes] = asyncio.Queue()
        for packet in packets or []:
            self._queue.put_nowait(packet)
        self.sent: list[bytes] = []

    async def send(self, payload: bytes) -> None:
        self.sent.append(payload)

    async def recv(self) -> bytes:
        return await self._queue.get()


class _FailingTransport:
    async def send(self, payload: bytes) -> None:
        _ = payload

    async def recv(self) -> bytes:
        raise ConnectionError("socket lost")


class _BlockingSendTransport(_FakeTransport):
    def __init__(self) -> None:
        super().__init__()
        self.send_started = asyncio.Event()
        self.release_send = asyncio.Event()

    async def send(self, payload: bytes) -> None:
        self.send_started.set()
        await self.release_send.wait()
        await super().send(payload)


def _make_inner_packet(msg_id: int, body: bytes, *, seqno: int = 1) -> bytes:
    return struct.pack("<qii", int(msg_id), int(seqno), len(body)) + body


def _server_msg_id(*, low_bits: int, seconds: int = 0) -> int:
    assert low_bits & 1 == 1
    return ((int(time.time()) + seconds) << 32) | low_bits


def _msg_container_body(messages: list[tuple[int, bytes]]) -> bytes:
    body = struct.pack("<ii", _MSG_CONTAINER_CONSTRUCTOR_ID, len(messages))
    for msg_id, payload in messages:
        body += struct.pack("<qii", msg_id, 1, len(payload)) + payload
    return body


def _rpc_result_body(req_msg_id: int, result_payload: bytes) -> bytes:
    return (
        struct.pack("<i", _RPC_RESULT_CONSTRUCTOR_ID)
        + struct.pack("<q", int(req_msg_id))
        + result_payload
    )


def _tl_bytes(data: bytes) -> bytes:
    ln = len(data)
    if ln < 254:
        out = bytes([ln]) + data
        out += b"\x00" * ((4 - ((1 + ln) % 4)) % 4)
        return out
    out = bytes([254]) + struct.pack("<I", ln)[:3] + data
    out += b"\x00" * ((4 - ((4 + ln) % 4)) % 4)
    return out


def _gzip_packed(payload: bytes) -> bytes:
    return struct.pack("<i", _GZIP_PACKED_CONSTRUCTOR_ID) + _tl_bytes(gzip.compress(payload))


def _build_sender_with_pending_calls() -> tuple[MtprotoEncryptedSender, _PendingCall, _PendingCall]:
    sender = MtprotoEncryptedSender(
        _FakeTransport(),
        state=_FakeState(),
        msg_id_gen=_FakeMsgIdGen(),
    )

    loop = asyncio.get_running_loop()
    call1 = _PendingCall(req_bytes=b"req1", future=loop.create_future())
    call1.msg_ids.add(101)
    sender._pending[101] = call1
    sender._sent[101] = (1, b"req1")

    call2 = _PendingCall(req_bytes=b"req2", future=loop.create_future())
    call2.msg_ids.add(202)
    sender._pending[202] = call2
    sender._sent[202] = (1, b"req2")

    return sender, call1, call2


def test_sender__decode_error__fails_only_relevant_call() -> None:
    async def _run() -> None:
        sender, call1, call2 = _build_sender_with_pending_calls()

        sender._fail_decode_for_req_ids(
            req_msg_ids={101},
            outer_msg_id=7001,
            error=TLCodecError("unknown constructor"),
        )

        with pytest.raises(RpcDecodeError):
            await call1.future
        assert not call2.future.done()

    asyncio.run(_run())


def test_sender__extract_req_msg_ids__unwraps_bounded_gzip() -> None:
    body = _gzip_packed(_rpc_result_body(101, struct.pack("<i", 6)))

    assert extract_req_msg_ids_from_payload(body) == {101}


def test_sender__extract_req_msg_ids__ignores_oversized_gzip() -> None:
    body = _gzip_packed(b"\x00" * (MAX_GZIP_UNPACKED_SIZE + 1))

    assert extract_req_msg_ids_from_payload(body) == set()


def test_sender__extract_req_msg_ids__ignores_malformed_gzip() -> None:
    body = struct.pack("<i", _GZIP_PACKED_CONSTRUCTOR_ID) + _tl_bytes(b"not gzip")

    assert extract_req_msg_ids_from_payload(body) == set()


def test_sender__unknown_constructor__poisons_connection_and_fails_all_pending() -> None:
    async def _run() -> None:
        req1 = 101
        req2 = 202

        bad_body = _rpc_result_body(req1, struct.pack("<i", 6))
        transport = _FakeTransport([_make_inner_packet(_server_msg_id(low_bits=1), bad_body)])
        incoming: asyncio.Queue[ReceivedMessage | ReceiverTerminated | UpdatesRecoveryRequired] = (
            asyncio.Queue()
        )
        sender = MtprotoEncryptedSender(
            transport,
            state=_FakeState(),
            msg_id_gen=_FakeMsgIdGen(),
            incoming_queue=incoming,
        )

        loop = asyncio.get_running_loop()
        call1 = _PendingCall(req_bytes=b"req1", future=loop.create_future())
        call1.msg_ids.add(req1)
        sender._pending[req1] = call1
        sender._sent[req1] = (1, b"req1")

        call2 = _PendingCall(req_bytes=b"req2", future=loop.create_future())
        call2.msg_ids.add(req2)
        sender._pending[req2] = call2
        sender._sent[req2] = (1, b"req2")

        await asyncio.wait_for(sender._recv_loop(), timeout=1.0)

        for future in (call1.future, call2.future):
            with pytest.raises(RpcDecodeError) as raised:
                await future
            assert raised.value.requires_reconnect is True
            assert raised.value.constructor_id == 6
            assert raised.value.path == "root.rpc_result"
        signal = incoming.get_nowait()
        assert isinstance(signal, ReceiverTerminated)
        assert signal.requires_reconnect is True
        assert signal.constructor_id == 6
        assert signal.path == "root.rpc_result"
        assert transport.sent == [], "an undecodable envelope must not be acknowledged"
        assert sender.is_healthy is False

    asyncio.run(_run())


def test_sender__nested_poll_unknown_preserves_path_and_requires_reconnect() -> None:
    async def _run() -> None:
        writer = TLWriter()
        writer.write_int(MessageMediaPoll.TL_ID)
        writer.write_object(
            Poll(
                id=777,
                flags=0,
                closed=False,
                public_voters=False,
                multiple_choice=False,
                quiz=False,
                open_answers=False,
                revoting_disabled=False,
                shuffle_answers=False,
                hide_results_until_close=False,
                creator=False,
                subscribers_only=False,
                question=TextWithEntities(text=b"Question", entities=[]),
                answers=[],
                close_period=None,
                close_date=None,
                countries_iso2=None,
                hash=0,
            )
        )
        writer.write_uint(0x12345678)
        transport = _FakeTransport(
            [_make_inner_packet(_server_msg_id(low_bits=1), writer.to_bytes())]
        )
        incoming: asyncio.Queue[ReceivedMessage | ReceiverTerminated | UpdatesRecoveryRequired] = (
            asyncio.Queue()
        )
        sender = MtprotoEncryptedSender(
            transport,
            state=_FakeState(),
            msg_id_gen=_FakeMsgIdGen(),
            incoming_queue=incoming,
        )

        await asyncio.wait_for(sender._recv_loop(), timeout=1.0)

        terminal = incoming.get_nowait()
        assert isinstance(terminal, ReceiverTerminated)
        assert isinstance(terminal.error, RpcDecodeError)
        assert terminal.error.requires_reconnect is True
        assert terminal.error.constructor_id == 0x12345678
        assert terminal.error.expected_type == "PollResults"
        assert terminal.error.path == "root.results"
        assert terminal.error.retryable is False
        assert transport.sent == []

    asyncio.run(_run())


def test_sender__trailing_bounded_tl_data_poison_is_not_acknowledged() -> None:
    async def _run() -> None:
        body = dumps(Pong(msg_id=1, ping_id=2)) + b"\x00\x00\x00\x00"
        transport = _FakeTransport([_make_inner_packet(_server_msg_id(low_bits=1), body)])
        incoming: asyncio.Queue[ReceivedMessage | ReceiverTerminated | UpdatesRecoveryRequired] = (
            asyncio.Queue()
        )
        sender = MtprotoEncryptedSender(
            transport,
            state=_FakeState(),
            msg_id_gen=_FakeMsgIdGen(),
            incoming_queue=incoming,
        )

        await asyncio.wait_for(sender._recv_loop(), timeout=1.0)

        terminal = incoming.get_nowait()
        assert isinstance(terminal, ReceiverTerminated)
        assert isinstance(terminal.error, RpcDecodeError)
        assert terminal.error.requires_reconnect is True
        assert terminal.error.constructor_id is None
        assert terminal.error.path == "root"
        assert transport.sent == []

    asyncio.run(_run())


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(dumps(Pong(msg_id=1, ping_id=2))[:-4], id="truncated-known-constructor"),
        pytest.param(
            struct.pack("<i", _GZIP_PACKED_CONSTRUCTOR_ID) + _tl_bytes(b"not gzip"),
            id="malformed-gzip",
        ),
    ],
)
def test_sender__any_authenticated_tl_decode_failure_poison_is_terminal(
    body: bytes,
) -> None:
    async def _run() -> None:
        transport = _FakeTransport([_make_inner_packet(_server_msg_id(low_bits=1), body)])
        incoming: asyncio.Queue[ReceivedMessage | ReceiverTerminated | UpdatesRecoveryRequired] = (
            asyncio.Queue()
        )
        sender = MtprotoEncryptedSender(
            transport,
            state=_FakeState(),
            msg_id_gen=_FakeMsgIdGen(),
            incoming_queue=incoming,
        )

        loop = asyncio.get_running_loop()
        pending: list[_PendingCall] = []
        for req_msg_id in (101, 202):
            call = _PendingCall(
                req_bytes=f"req-{req_msg_id}".encode(),
                future=loop.create_future(),
            )
            call.msg_ids.add(req_msg_id)
            sender._pending[req_msg_id] = call
            sender._sent[req_msg_id] = (1, call.req_bytes)
            pending.append(call)

        await asyncio.wait_for(sender._recv_loop(), timeout=1.0)

        failures: list[RpcDecodeError] = []
        for call in pending:
            with pytest.raises(RpcDecodeError) as raised:
                await call.future
            failures.append(raised.value)
            assert raised.value.requires_reconnect is True
            assert raised.value.retryable is False
            assert raised.value.path == "root"

        terminal = incoming.get_nowait()
        assert isinstance(terminal, ReceiverTerminated)
        assert terminal.error is failures[0]
        assert all(failure is terminal.error for failure in failures)
        assert terminal.requires_reconnect is True
        assert transport.sent == [], "a malformed authenticated envelope must never be ACKed"
        assert sender.is_healthy is False
        assert sender._pending == {}
        assert sender._sent == {}

    asyncio.run(_run())


def test_sender__authenticated_inner_length_failure_is_terminal_decode_poison() -> None:
    async def _run() -> None:
        # decrypt_packet has returned successfully, but the declared body length
        # crosses the authenticated inner-message boundary.
        malformed_inner = (
            struct.pack("<qii", _server_msg_id(low_bits=1), 1, 8) + b"\x00\x00\x00\x00"
        )
        transport = _FakeTransport([malformed_inner])
        incoming: asyncio.Queue[ReceivedMessage | ReceiverTerminated | UpdatesRecoveryRequired] = (
            asyncio.Queue()
        )
        sender = MtprotoEncryptedSender(
            transport,
            state=_FakeState(),
            msg_id_gen=_FakeMsgIdGen(),
            incoming_queue=incoming,
        )
        loop = asyncio.get_running_loop()
        calls: list[_PendingCall] = []
        for req_msg_id in (101, 202):
            call = _PendingCall(req_bytes=b"request", future=loop.create_future())
            call.msg_ids.add(req_msg_id)
            sender._pending[req_msg_id] = call
            sender._sent[req_msg_id] = (1, call.req_bytes)
            calls.append(call)

        await asyncio.wait_for(sender._recv_loop(), timeout=1.0)

        failures: list[RpcDecodeError] = []
        for call in calls:
            with pytest.raises(RpcDecodeError) as raised:
                await call.future
            failures.append(raised.value)
            assert raised.value.requires_reconnect is True
            assert raised.value.retryable is False
            assert raised.value.path == "mtproto.inner_message"
            assert "outer_msg_id=unavailable" in str(raised.value)

        terminal = incoming.get_nowait()
        assert isinstance(terminal, ReceiverTerminated)
        assert terminal.error is failures[0]
        assert all(failure is terminal.error for failure in failures)
        assert terminal.requires_reconnect is True
        assert transport.sent == []
        assert sender.is_healthy is False

    asyncio.run(_run())


def test_sender__unauthenticated_decrypt_failure_is_not_mislabeled_tl_decode() -> None:
    class RejectingState(_FakeState):
        def decrypt_packet(self, packet: bytes, *, from_server: bool) -> bytes:
            _ = packet, from_server
            raise MtprotoStateError("msg_key mismatch after decryption")

    async def _run() -> None:
        transport = _FakeTransport([b"unauthenticated"])
        incoming: asyncio.Queue[ReceivedMessage | ReceiverTerminated | UpdatesRecoveryRequired] = (
            asyncio.Queue()
        )
        sender = MtprotoEncryptedSender(
            transport,
            state=RejectingState(),
            msg_id_gen=_FakeMsgIdGen(),
            incoming_queue=incoming,
        )

        await asyncio.wait_for(sender._recv_loop(), timeout=1.0)

        terminal = incoming.get_nowait()
        assert isinstance(terminal, ReceiverTerminated)
        assert isinstance(terminal.error, RpcSenderError)
        assert not isinstance(terminal.error, RpcDecodeError)
        assert terminal.requires_reconnect is False
        assert isinstance(terminal.error.__cause__, MtprotoStateError)
        assert transport.sent == []
        assert sender.is_healthy is False

    asyncio.run(_run())


def test_sender__decode_error__does_not_drop_all_pending() -> None:
    async def _run() -> None:
        sender, call1, call2 = _build_sender_with_pending_calls()

        sender._fail_decode_for_req_ids(
            req_msg_ids={101},
            outer_msg_id=7001,
            error=TLCodecError("unknown constructor"),
        )

        assert call1.future.done()
        assert 202 in sender._pending
        assert sender._pending[202] is call2
        assert not call2.future.done()

    asyncio.run(_run())


def test_sender__receiver_failure_propagates_to_pending_call_and_update_consumer() -> None:
    async def _run() -> None:
        incoming: asyncio.Queue[ReceivedMessage | ReceiverTerminated] = asyncio.Queue()
        sender = MtprotoEncryptedSender(
            _FailingTransport(),
            state=_FakeState(),
            msg_id_gen=_FakeMsgIdGen(),
            incoming_queue=incoming,
        )
        loop = asyncio.get_running_loop()
        call = _PendingCall(req_bytes=b"req", future=loop.create_future())
        call.msg_ids.add(101)
        sender._pending[101] = call
        sender._sent[101] = (1, b"req")

        await sender._recv_loop()

        with pytest.raises(RpcSenderError, match="socket lost"):
            await call.future
        terminal = incoming.get_nowait()
        assert isinstance(terminal, ReceiverTerminated)
        assert terminal.error is sender.terminal_error
        assert sender.is_healthy is False
        with pytest.raises(RpcSenderError, match="socket lost"):
            sender._ensure_recv_task()

    asyncio.run(_run())


def test_sender__incoming_queue_overflow_requests_recovery_without_blocking_rpc() -> None:
    async def _run() -> None:
        existing = ReceivedMessage(msg_id=1, seqno=1, obj=object())
        incoming: asyncio.Queue[ReceivedMessage | ReceiverTerminated] = asyncio.Queue(maxsize=1)
        incoming.put_nowait(existing)
        sender = MtprotoEncryptedSender(
            _FakeTransport(),
            state=_FakeState(),
            msg_id_gen=_FakeMsgIdGen(),
            incoming_queue=incoming,
        )
        update = ReceivedMessage(msg_id=2, seqno=1, obj=object())

        await asyncio.wait_for(sender._handle_message(update), timeout=1.0)
        signal = await incoming.get()
        assert signal == UpdatesRecoveryRequired(reason="incoming_queue_overflow")

    asyncio.run(_run())


def test_sender__terminal_signal_replaces_full_queue_without_deadlocking_receiver() -> None:
    async def _run() -> None:
        queued = ReceivedMessage(msg_id=1, seqno=1, obj=object())
        incoming: asyncio.Queue[ReceivedMessage | ReceiverTerminated] = asyncio.Queue(maxsize=1)
        incoming.put_nowait(queued)
        sender = MtprotoEncryptedSender(
            _FailingTransport(),
            state=_FakeState(),
            msg_id_gen=_FakeMsgIdGen(),
            incoming_queue=incoming,
        )

        recv_task = asyncio.create_task(sender._recv_loop())
        await asyncio.sleep(0)
        await asyncio.wait_for(recv_task, timeout=1.0)
        terminal = await incoming.get()
        assert isinstance(terminal, ReceiverTerminated)
        assert isinstance(terminal.error, RpcSenderError)

    asyncio.run(_run())


def test_sender__close_is_idempotent_and_fails_pending_calls() -> None:
    async def _run() -> None:
        sender, call1, call2 = _build_sender_with_pending_calls()

        await sender.close()
        await sender.close()

        with pytest.raises(RpcSenderError, match="closed"):
            await call1.future
        with pytest.raises(RpcSenderError, match="closed"):
            await call2.future
        assert sender.is_healthy is False
        assert sender._pending == {}
        assert sender._sent == {}

    asyncio.run(_run())


def test_sender__registers_call_before_send_can_receive_fast_response() -> None:
    async def _run() -> None:
        transport = _BlockingSendTransport()
        sender = MtprotoEncryptedSender(
            transport,
            state=_FakeState(),
            msg_id_gen=_FakeMsgIdGen(),
        )
        call = _PendingCall(
            req_bytes=b"request",
            future=asyncio.get_running_loop().create_future(),
        )

        send_task = asyncio.create_task(sender._send_new_attempt(call))
        await transport.send_started.wait()

        await sender._handle_message(
            ReceivedMessage(msg_id=777, seqno=1, obj=Pong(msg_id=9004, ping_id=1234))
        )
        response = await asyncio.wait_for(call.future, timeout=1.0)
        assert isinstance(response, Pong)
        assert int(response.ping_id) == 1234

        transport.release_send.set()
        assert await send_task == 9004
        sender._cleanup_call(call)

    asyncio.run(_run())


def test_sender__rpc_timeout_does_not_blindly_resend_non_idempotent_request() -> None:
    async def _run() -> None:
        transport = _FakeTransport()
        sender = MtprotoEncryptedSender(
            transport,
            state=_FakeState(),
            msg_id_gen=_FakeMsgIdGen(),
        )

        with pytest.raises(RpcSenderError, match="Timed out waiting"):
            await sender._invoke_tl_once(
                object(),
                dumps_fn=lambda _: b"req!",
                timeout=0.01,
            )

        assert len(transport.sent) == 1
        assert sender._pending == {}
        assert sender._sent == {}

    asyncio.run(_run())


def test_sender__clock_skew_bad_msg_is_accepted_and_request_is_retried() -> None:
    async def _run() -> None:
        request_msg_id = 101
        server_msg_id = _server_msg_id(low_bits=1, seconds=3_600)
        bad_msg = dumps(
            BadMsgNotification(
                bad_msg_id=request_msg_id,
                bad_msg_seqno=1,
                error_code=16,
            )
        )
        transport = _FakeTransport([_make_inner_packet(server_msg_id, bad_msg)])
        msg_id_gen = _FakeMsgIdGen()
        sender = MtprotoEncryptedSender(
            transport,
            state=_FakeState(),
            msg_id_gen=msg_id_gen,
        )
        call = _PendingCall(
            req_bytes=b"req!",
            future=asyncio.get_running_loop().create_future(),
            attempts=1,
            active_msg_id=request_msg_id,
        )
        call.msg_ids.add(request_msg_id)
        sender._pending[request_msg_id] = call
        sender._sent[request_msg_id] = (1, call.req_bytes)

        task = asyncio.create_task(sender._recv_loop())
        try:
            for _ in range(100):
                if call.attempts == 2:
                    break
                await asyncio.sleep(0.001)

            assert call.attempts == 2
            assert msg_id_gen.synchronized == [server_msg_id]
            assert server_msg_id in sender._received_msg_ids
            assert call.future.done() is False
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            sender._cleanup_call(call)

    asyncio.run(_run())


def test_sender__normal_window_clock_correction_keeps_server_msg_id_floor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _run() -> None:
        frozen_time = 1_700_000_000.5
        monkeypatch.setattr(
            "telecraft.mtproto.core.msg_id.time.time",
            lambda: frozen_time,
        )
        correction_msg_id = (1_700_000_000 << 32) | 0xF0000001
        request_msg_id = 101
        transport = _FakeTransport()
        msg_id_gen = MsgIdGenerator()
        sender = MtprotoEncryptedSender(
            transport,
            state=_FakeState(),
            msg_id_gen=msg_id_gen,
        )
        call = _PendingCall(
            req_bytes=b"req!",
            future=asyncio.get_running_loop().create_future(),
            attempts=1,
            active_msg_id=request_msg_id,
        )
        call.msg_ids.add(request_msg_id)
        sender._pending[request_msg_id] = call
        sender._sent[request_msg_id] = (1, call.req_bytes)

        await sender._handle_message(
            ReceivedMessage(
                msg_id=correction_msg_id,
                seqno=1,
                obj=BadMsgNotification(
                    bad_msg_id=request_msg_id,
                    bad_msg_seqno=1,
                    error_code=16,
                ),
            )
        )

        assert call.active_msg_id is not None
        assert call.active_msg_id > correction_msg_id
        sender._cleanup_call(call)

    asyncio.run(_run())


def test_sender__clock_skew_bad_msg_must_match_a_recent_pending_call() -> None:
    async def _run() -> None:
        server_msg_id = _server_msg_id(low_bits=1, seconds=3_600)
        bad_msg = dumps(
            BadMsgNotification(
                bad_msg_id=999_999,
                bad_msg_seqno=1,
                error_code=16,
            )
        )
        transport = _FakeTransport([_make_inner_packet(server_msg_id, bad_msg)])
        msg_id_gen = _FakeMsgIdGen()
        sender = MtprotoEncryptedSender(
            transport,
            state=_FakeState(),
            msg_id_gen=msg_id_gen,
        )

        task = asyncio.create_task(sender._recv_loop())
        try:
            await asyncio.sleep(0.01)
            assert msg_id_gen.synchronized == []
            assert sender._received_msg_ids == set()
            assert transport.sent == []
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    asyncio.run(_run())


def test_sender__clock_skew_bad_msg_inside_container_retries_request() -> None:
    async def _run() -> None:
        request_msg_id = 101
        correction_msg_id = _server_msg_id(low_bits=1, seconds=3_600)
        outer_msg_id = _server_msg_id(low_bits=5, seconds=3_600)
        bad_msg = dumps(
            BadMsgNotification(
                bad_msg_id=request_msg_id,
                bad_msg_seqno=1,
                error_code=17,
            )
        )
        container = _msg_container_body([(correction_msg_id, bad_msg)])
        transport = _FakeTransport([_make_inner_packet(outer_msg_id, container)])
        msg_id_gen = _FakeMsgIdGen()
        sender = MtprotoEncryptedSender(
            transport,
            state=_FakeState(),
            msg_id_gen=msg_id_gen,
        )
        call = _PendingCall(
            req_bytes=b"req!",
            future=asyncio.get_running_loop().create_future(),
            attempts=1,
            active_msg_id=request_msg_id,
        )
        call.msg_ids.add(request_msg_id)
        sender._pending[request_msg_id] = call
        sender._sent[request_msg_id] = (1, call.req_bytes)

        task = asyncio.create_task(sender._recv_loop())
        try:
            for _ in range(100):
                if call.attempts == 2:
                    break
                await asyncio.sleep(0.001)

            assert call.attempts == 2
            assert msg_id_gen.synchronized == [correction_msg_id]
            assert sender._received_msg_ids == {correction_msg_id, outer_msg_id}
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            sender._cleanup_call(call)

    asyncio.run(_run())


def test_sender__stale_bad_server_salt_cannot_mutate_session_or_resend() -> None:
    async def _run() -> None:
        transport = _FakeTransport()
        state = _FakeState(server_salt=b"old-salt")
        sender = MtprotoEncryptedSender(
            transport,
            state=state,
            msg_id_gen=_FakeMsgIdGen(),
        )
        call = _PendingCall(
            req_bytes=b"req!",
            future=asyncio.get_running_loop().create_future(),
            attempts=2,
            active_msg_id=202,
        )
        call.msg_ids.update({101, 202})
        sender._pending.update({101: call, 202: call})
        sender._sent.update({101: (1, call.req_bytes), 202: (3, call.req_bytes)})

        await sender._handle_message(
            ReceivedMessage(
                msg_id=_server_msg_id(low_bits=1),
                seqno=1,
                obj=BadServerSalt(
                    bad_msg_id=101,
                    bad_msg_seqno=1,
                    error_code=48,
                    new_server_salt=123,
                ),
            )
        )

        assert state.server_salt == b"old-salt"
        assert transport.sent == []
        assert call.future.done() is False
        sender._cleanup_call(call)

    asyncio.run(_run())


def test_sender__salt_and_time_recovery_have_independent_retry_budgets() -> None:
    async def _run() -> None:
        request_msg_id = 101
        transport = _FakeTransport()
        msg_id_gen = _FakeMsgIdGen()
        sender = MtprotoEncryptedSender(
            transport,
            state=_FakeState(),
            msg_id_gen=msg_id_gen,
        )
        call = _PendingCall(
            req_bytes=b"req!",
            future=asyncio.get_running_loop().create_future(),
            attempts=1,
            active_msg_id=request_msg_id,
        )
        call.msg_ids.add(request_msg_id)
        sender._pending[request_msg_id] = call
        sender._sent[request_msg_id] = (1, call.req_bytes)

        await sender._handle_message(
            ReceivedMessage(
                msg_id=_server_msg_id(low_bits=1),
                seqno=1,
                obj=BadServerSalt(
                    bad_msg_id=request_msg_id,
                    bad_msg_seqno=1,
                    error_code=48,
                    new_server_salt=123,
                ),
            )
        )
        after_salt_msg_id = call.active_msg_id
        assert after_salt_msg_id is not None
        after_salt_seqno = sender._sent[after_salt_msg_id][0]

        await sender._handle_message(
            ReceivedMessage(
                msg_id=_server_msg_id(low_bits=5),
                seqno=1,
                obj=BadMsgNotification(
                    bad_msg_id=after_salt_msg_id,
                    bad_msg_seqno=after_salt_seqno,
                    error_code=16,
                ),
            )
        )

        assert call.attempts == 3
        assert call.bad_salt_retries == 1
        assert call.bad_time_retries == 1
        assert len(transport.sent) == 2
        assert call.future.done() is False
        sender._cleanup_call(call)

    asyncio.run(_run())


def test_sender__close_does_not_deadlock_behind_blocked_send() -> None:
    async def _run() -> None:
        transport = _BlockingSendTransport()
        sender = MtprotoEncryptedSender(
            transport,
            state=_FakeState(),
            msg_id_gen=_FakeMsgIdGen(),
        )
        call = _PendingCall(
            req_bytes=b"request",
            future=asyncio.get_running_loop().create_future(),
        )

        send_task = asyncio.create_task(sender._send_new_attempt(call))
        await transport.send_started.wait()
        await asyncio.wait_for(sender.close(), timeout=1.0)

        with pytest.raises(RpcSenderError, match="closed"):
            await call.future
        transport.release_send.set()
        with pytest.raises(RpcSenderError, match="closed"):
            await send_task

        assert sender._pending == {}
        assert sender._sent == {}

    asyncio.run(_run())


def test_sender__server_msg_ids_enforce_parity_time_and_replay_rules() -> None:
    sender = MtprotoEncryptedSender(
        _FakeTransport(),
        state=_FakeState(),
        msg_id_gen=_FakeMsgIdGen(),
    )
    now = 1_700_000_000
    valid_past_boundary = ((now - 300) << 32) | 1
    valid_future_boundary = ((now + 30) << 32) | 3
    invalid_even = (now << 32) | 2
    invalid_past = ((now - 301) << 32) | 5
    invalid_future = ((now + 31) << 32) | 7

    accepted = sender._accept_server_msg_ids(
        [0, invalid_even, invalid_past, invalid_future, valid_past_boundary, valid_future_boundary],
        now=now,
    )

    assert accepted == {valid_past_boundary, valid_future_boundary}
    assert sender._accept_server_msg_ids([valid_future_boundary], now=now) == set()


def test_sender__server_msg_id_cache_is_bounded_and_rejects_older_ids() -> None:
    sender = MtprotoEncryptedSender(
        _FakeTransport(),
        state=_FakeState(),
        msg_id_gen=_FakeMsgIdGen(),
    )
    now = 1_700_000_000
    msg_ids = [(now << 32) | (index * 2 + 1) for index in range(1100)]

    assert sender._accept_server_msg_ids(msg_ids, now=now) == set(msg_ids)
    assert len(sender._received_msg_ids) == 1024
    assert min(sender._received_msg_ids) == msg_ids[-1024]
    assert sender._accept_server_msg_ids([msg_ids[0]], now=now) == set()


def test_sender__nested_container_length_must_be_divisible_by_four() -> None:
    body = (
        struct.pack("<ii", _MSG_CONTAINER_CONSTRUCTOR_ID, 1)
        + struct.pack("<qii", _server_msg_id(low_bits=1), 1, 3)
        + b"bad"
    )

    with pytest.raises(RpcSenderError, match="divisible by 4"):
        _validate_nested_message_lengths(body)


def test_sender__duplicate_outer_msg_id_is_ignored_without_stopping_receiver() -> None:
    async def _run() -> None:
        first_msg_id = _server_msg_id(low_bits=1)
        second_msg_id = _server_msg_id(low_bits=5)
        update = dumps(UpdateConfig())
        transport = _FakeTransport(
            [
                _make_inner_packet(first_msg_id, update),
                _make_inner_packet(first_msg_id, update),
                _make_inner_packet(second_msg_id, update),
            ]
        )
        incoming: asyncio.Queue[ReceivedMessage | ReceiverTerminated] = asyncio.Queue()
        msg_id_gen = _FakeMsgIdGen()
        sender = MtprotoEncryptedSender(
            transport,
            state=_FakeState(),
            msg_id_gen=msg_id_gen,
            incoming_queue=incoming,
        )

        task = asyncio.create_task(sender._recv_loop())
        try:
            first = await asyncio.wait_for(incoming.get(), timeout=1.0)
            second = await asyncio.wait_for(incoming.get(), timeout=1.0)
            assert isinstance(first, ReceivedMessage)
            assert isinstance(second, ReceivedMessage)
            assert [first.msg_id, second.msg_id] == [first_msg_id, second_msg_id]
            assert msg_id_gen.observed == [first_msg_id, second_msg_id]
            assert len(transport.sent) == 2
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    asyncio.run(_run())


def test_sender__container_ids_are_validated_against_one_cache_snapshot() -> None:
    async def _run() -> None:
        inner_first = _server_msg_id(low_bits=1)
        inner_second = _server_msg_id(low_bits=5)
        outer = _server_msg_id(low_bits=21)
        update = dumps(UpdateConfig())
        container = _msg_container_body([(inner_first, update), (inner_second, update)])
        transport = _FakeTransport([_make_inner_packet(outer, container)])
        incoming: asyncio.Queue[ReceivedMessage | ReceiverTerminated] = asyncio.Queue()
        sender = MtprotoEncryptedSender(
            transport,
            state=_FakeState(),
            msg_id_gen=_FakeMsgIdGen(),
            incoming_queue=incoming,
        )

        task = asyncio.create_task(sender._recv_loop())
        try:
            first = await asyncio.wait_for(incoming.get(), timeout=1.0)
            second = await asyncio.wait_for(incoming.get(), timeout=1.0)
            assert isinstance(first, ReceivedMessage)
            assert isinstance(second, ReceivedMessage)
            assert [first.msg_id, second.msg_id] == [inner_first, inner_second]
            assert sender._received_msg_ids == {inner_first, inner_second, outer}
            assert len(transport.sent) == 1
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    asyncio.run(_run())
