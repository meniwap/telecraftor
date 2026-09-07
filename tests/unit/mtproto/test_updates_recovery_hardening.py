from __future__ import annotations

import asyncio
import contextlib
import struct
import time
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest

import telecraft.client.mtproto as mtproto_module
import telecraft.mtproto.updates.engine as updates_engine_module
from telecraft.client.mtproto import (
    ClientInit,
    MtprotoClient,
    UpdatesRecoveryExhaustedError,
)
from telecraft.mtproto.rpc.sender import (
    MtprotoEncryptedSender,
    ReceivedMessage,
    ReceiverTerminated,
    RpcDecodeError,
    UpdatesRecoveryRequired,
)
from telecraft.mtproto.updates.engine import UpdatesEngine, UpdatesEngineError
from telecraft.mtproto.updates.state import UpdatesState
from telecraft.tl.generated.functions import (
    HelpGetConfig,
    InitConnection,
    InvokeWithLayer,
    UpdatesGetChannelDifference,
    UpdatesGetDifference,
    UpdatesGetState,
)
from telecraft.tl.generated.types import (
    InputChannel,
    NewSessionCreated,
    UpdateChannelTooLong,
    UpdateConfig,
    UpdatePtsChanged,
    Updates,
    UpdatesChannelDifferenceEmpty,
    UpdatesDifference,
    UpdatesDifferenceEmpty,
    UpdatesDifferenceSlice,
    UpdatesDifferenceTooLong,
    UpdateShort,
)
from telecraft.tl.generated.types import UpdatesState as TlUpdatesState

_LAYER_216_MESSAGE_CONSTRUCTOR_ID = -1743401272  # 0x9815cec8


def _tl_state(*, pts: int, qts: int, date: int, seq: int) -> TlUpdatesState:
    return TlUpdatesState(
        pts=pts,
        qts=qts,
        date=date,
        seq=seq,
        unread_count=0,
    )


def test_update_pts_changed_refreshes_authoritative_state_without_delivery() -> None:
    calls: list[Any] = []

    async def invoke(req: Any) -> Any:
        calls.append(req)
        return _tl_state(pts=91, qts=7, date=300, seq=12)

    engine = UpdatesEngine(invoke_api=invoke)
    engine.state = UpdatesState(pts=10, qts=2, date=100, seq=3)

    applied = asyncio.run(engine.apply(UpdatePtsChanged()))

    assert len(calls) == 1
    assert isinstance(calls[0], UpdatesGetState)
    assert applied.updates == []
    assert applied.new_messages == []
    assert engine.state == UpdatesState(pts=91, qts=7, date=300, seq=12)


def test_update_short_pts_changed_refreshes_state_instead_of_emitting_marker() -> None:
    async def invoke(req: Any) -> Any:
        assert isinstance(req, UpdatesGetState)
        return _tl_state(pts=91, qts=7, date=300, seq=12)

    engine = UpdatesEngine(invoke_api=invoke)
    engine.state = UpdatesState(pts=10, qts=2, date=100, seq=3)

    applied = asyncio.run(engine.apply(UpdateShort(update=UpdatePtsChanged(), date=200)))

    assert applied.updates == []
    assert engine.state == UpdatesState(pts=91, qts=7, date=300, seq=12)


def test_pts_changed_envelope_still_recovers_independent_channel_marker() -> None:
    calls: list[Any] = []

    async def invoke(req: Any) -> Any:
        calls.append(req)
        if isinstance(req, UpdatesGetState):
            return _tl_state(pts=91, qts=7, date=300, seq=12)
        return UpdatesChannelDifferenceEmpty(
            flags=1,
            final=True,
            pts=80,
            timeout=None,
        )

    engine = UpdatesEngine(invoke_api=invoke)
    engine.state = UpdatesState(pts=10, qts=2, date=100, seq=3)
    ordinary = UpdateConfig()
    user = SimpleNamespace(id=5)
    channel = SimpleNamespace(id=100, access_hash=123, min=False)
    envelope = Updates(
        updates=[
            UpdatePtsChanged(),
            ordinary,
            UpdateChannelTooLong(flags=1, channel_id=100, pts=73),
        ],
        users=[user],
        chats=[channel],
        date=200,
        seq=4,
    )

    applied = asyncio.run(engine.apply(envelope))

    assert applied.updates == [ordinary]
    assert applied.users == [user]
    assert applied.chats == [channel]
    assert [type(req) for req in calls] == [
        UpdatesGetState,
        UpdatesGetChannelDifference,
    ]
    assert calls[1].pts == 73
    assert engine._channel_pts[100] == 80


def test_pts_changed_envelope_preserves_fresh_pts_and_qts_sibling_payloads() -> None:
    calls: list[Any] = []

    async def invoke(req: Any) -> Any:
        calls.append(req)
        return _tl_state(pts=11, qts=3, date=300, seq=12)

    engine = UpdatesEngine(invoke_api=invoke)
    engine.state = UpdatesState(pts=10, qts=2, date=100, seq=3)
    pts_update = SimpleNamespace(TL_NAME="updateNewMessage", pts=11, pts_count=1)
    qts_update = SimpleNamespace(TL_NAME="updateEncryptedMessagesRead", qts=3)
    envelope = Updates(
        updates=[UpdatePtsChanged(), pts_update, qts_update],
        users=[],
        chats=[],
        date=200,
        seq=4,
    )

    applied = asyncio.run(engine.apply(envelope))

    assert len(calls) == 1
    assert isinstance(calls[0], UpdatesGetState)
    assert applied.updates == [pts_update, qts_update]
    assert engine.state == UpdatesState(pts=11, qts=3, date=300, seq=12)


def test_pts_changed_gap_recovers_before_refresh_without_dropping_siblings() -> None:
    calls: list[Any] = []
    accepted_update = SimpleNamespace(TL_NAME="updateNewMessage", pts=11, pts_count=1)
    missing_update = SimpleNamespace(TL_NAME="updateNewMessage", pts=12, pts_count=1)
    gap_update = SimpleNamespace(TL_NAME="updateNewMessage", pts=13, pts_count=1)
    ordinary = UpdateConfig()

    async def invoke(req: Any) -> Any:
        calls.append(req)
        if isinstance(req, UpdatesGetDifference):
            assert req.pts == 10
            return UpdatesDifference(
                new_messages=[],
                new_encrypted_messages=[],
                other_updates=[accepted_update, missing_update, gap_update],
                chats=[],
                users=[],
                state=_tl_state(pts=13, qts=2, date=250, seq=5),
            )
        assert isinstance(req, UpdatesGetState)
        return _tl_state(pts=13, qts=7, date=300, seq=12)

    engine = UpdatesEngine(invoke_api=invoke)
    engine.state = UpdatesState(pts=10, qts=2, date=100, seq=3)
    envelope = Updates(
        updates=[UpdatePtsChanged(), accepted_update, gap_update, ordinary],
        users=[],
        chats=[],
        date=200,
        seq=4,
    )

    applied = asyncio.run(engine.apply(envelope))

    assert [type(call) for call in calls] == [UpdatesGetDifference, UpdatesGetState]
    assert applied.updates == [accepted_update, missing_update, gap_update, ordinary]
    assert applied.updates.count(accepted_update) == 1
    assert engine.state == UpdatesState(pts=13, qts=7, date=300, seq=12)


@pytest.mark.parametrize(
    ("stored_pts", "expected_pts", "expected_force"),
    [(None, 73, True), (50, 50, False)],
)
def test_update_channel_too_long_uses_embedded_pts_only_without_local_cursor(
    stored_pts: int | None,
    expected_pts: int,
    expected_force: bool,
) -> None:
    calls: list[Any] = []

    async def invoke(req: Any) -> Any:
        calls.append(req)
        return UpdatesChannelDifferenceEmpty(
            flags=1,
            final=True,
            pts=80,
            timeout=None,
        )

    engine = UpdatesEngine(
        invoke_api=invoke,
        resolve_input_channel=lambda channel_id: InputChannel(
            channel_id=channel_id,
            access_hash=123,
        ),
    )
    engine.state = UpdatesState(pts=10, qts=0, date=100, seq=3)
    if stored_pts is not None:
        engine._channel_pts[100] = stored_pts

    asyncio.run(engine.apply(UpdateChannelTooLong(flags=1, channel_id=100, pts=73)))

    assert len(calls) == 1
    assert isinstance(calls[0], UpdatesGetChannelDifference)
    assert calls[0].pts == expected_pts
    assert calls[0].force is expected_force
    assert engine._channel_pts[100] == 80


def test_difference_too_long_refetches_from_new_common_pts() -> None:
    calls: list[Any] = []

    async def invoke(req: Any) -> Any:
        calls.append(req)
        if len(calls) == 1:
            return UpdatesDifferenceTooLong(pts=999)
        return UpdatesDifferenceEmpty(date=101, seq=4)

    engine = UpdatesEngine(invoke_api=invoke)
    engine.state = UpdatesState(pts=10, qts=7, date=100, seq=3)

    applied = asyncio.run(engine.recover())

    assert len(calls) == 2
    assert all(isinstance(call, UpdatesGetDifference) for call in calls)
    assert calls[0].pts == 10
    assert calls[1].pts == 999
    assert applied.updates == []
    assert engine.state == UpdatesState(pts=999, qts=7, date=101, seq=4)


def test_difference_too_long_without_progress_fails_transactionally() -> None:
    initial = UpdatesState(pts=10, qts=7, date=100, seq=3)

    async def invoke(_req: Any) -> Any:
        return UpdatesDifferenceTooLong(pts=10)

    engine = UpdatesEngine(invoke_api=invoke)
    engine.state = initial

    with pytest.raises(UpdatesEngineError, match="no common pts progress"):
        asyncio.run(engine.recover())

    assert engine.state == initial


def test_difference_slice_without_state_progress_fails_transactionally() -> None:
    initial = UpdatesState(pts=10, qts=7, date=100, seq=3)

    async def invoke(_req: Any) -> Any:
        return UpdatesDifferenceSlice(
            new_messages=[],
            new_encrypted_messages=[],
            other_updates=[],
            chats=[],
            users=[],
            intermediate_state=_tl_state(pts=10, qts=7, date=100, seq=3),
        )

    engine = UpdatesEngine(invoke_api=invoke)
    engine.state = initial

    with pytest.raises(UpdatesEngineError, match="made no state progress"):
        asyncio.run(engine.recover())

    assert engine.state == initial


def test_difference_pagination_has_a_transactional_page_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    monkeypatch.setattr(updates_engine_module, "_MAX_DIFFERENCE_PAGES", 2)

    async def invoke(req: Any) -> Any:
        nonlocal calls
        calls += 1
        return UpdatesDifferenceSlice(
            new_messages=[],
            new_encrypted_messages=[],
            other_updates=[],
            chats=[],
            users=[],
            intermediate_state=_tl_state(
                pts=int(req.pts) + 1,
                qts=int(req.qts),
                date=int(req.date),
                seq=3,
            ),
        )

    initial = UpdatesState(pts=10, qts=7, date=100, seq=3)
    engine = UpdatesEngine(invoke_api=invoke)
    engine.state = initial

    with pytest.raises(UpdatesEngineError, match="Too many"):
        asyncio.run(engine.recover())

    assert calls == 2
    assert engine.state == initial


def test_startup_difference_decode_failure_restores_durable_checkpoint() -> None:
    initial = UpdatesState(
        pts=10,
        qts=7,
        date=100,
        seq=3,
        channel_pts={100: 44},
    )
    calls = 0

    async def invoke(_req: Any) -> Any:
        nonlocal calls
        calls += 1
        if calls == 1:
            return UpdatesDifferenceSlice(
                new_messages=[],
                new_encrypted_messages=[],
                other_updates=[],
                chats=[],
                users=[],
                intermediate_state=_tl_state(pts=11, qts=7, date=101, seq=4),
            )
        raise RpcDecodeError(
            "legacy message",
            constructor_id=_LAYER_216_MESSAGE_CONSTRUCTOR_ID,
            path="root.rpc_result.new_messages[0]",
            position=64,
            requires_reconnect=True,
        )

    engine = UpdatesEngine(invoke_api=invoke)
    with pytest.raises(RpcDecodeError):
        asyncio.run(engine.initialize(initial_state=initial))

    assert engine.checkpoint() == initial


@dataclass
class _FakeState:
    server_salt: bytes = b"\x00" * 8

    def decrypt_packet(self, packet: bytes, *, from_server: bool) -> bytes:
        _ = from_server
        return packet

    def encrypt_inner_message(self, inner: bytes, *, to_server: bool) -> bytes:
        _ = to_server
        return inner

    def next_seq_no(self, *, content_related: bool) -> int:
        _ = content_related
        return 0


class _FakeMsgIdGen:
    def __init__(self) -> None:
        self.value = 9001
        self._now = time.time()

    def next(self) -> int:
        self.value += 4
        return self.value

    def observe(self, msg_id: int) -> None:
        _ = msg_id

    def now(self) -> float:
        return self._now

    def synchronize_from_msg_id(
        self,
        server_msg_id: int,
        *,
        reset_last: bool = True,
    ) -> None:
        _ = reset_last
        self._now = float(int(server_msg_id) >> 32)


class _FakeTransport:
    def __init__(self, packets: list[bytes] | None = None) -> None:
        self.queue: asyncio.Queue[bytes] = asyncio.Queue()
        for packet in packets or []:
            self.queue.put_nowait(packet)
        self.sent: list[bytes] = []

    async def recv(self) -> bytes:
        return await self.queue.get()

    async def send(self, payload: bytes) -> None:
        self.sent.append(payload)


def _server_msg_id() -> int:
    return (int(time.time()) << 32) | 1


def _inner_packet(msg_id: int, body: bytes) -> bytes:
    return struct.pack("<qii", msg_id, 1, len(body)) + body


def test_new_session_created_updates_salt_and_requests_recovery() -> None:
    async def run() -> None:
        incoming: asyncio.Queue[ReceivedMessage | ReceiverTerminated | UpdatesRecoveryRequired] = (
            asyncio.Queue()
        )
        state = _FakeState()
        sender = MtprotoEncryptedSender(
            _FakeTransport(),
            state=state,
            msg_id_gen=_FakeMsgIdGen(),
            incoming_queue=incoming,
        )

        await sender._handle_message(
            ReceivedMessage(
                msg_id=1,
                seqno=1,
                obj=NewSessionCreated(
                    first_msg_id=1,
                    unique_id=2,
                    server_salt=-2,
                ),
            )
        )

        assert state.server_salt == ((1 << 64) - 2).to_bytes(8, "little")
        assert incoming.get_nowait() == UpdatesRecoveryRequired(reason="new_session_created")

    asyncio.run(run())


def test_undecodable_incoming_payload_requests_updates_recovery() -> None:
    async def run() -> None:
        bad_body = struct.pack("<I", 0x12345678)
        transport = _FakeTransport([_inner_packet(_server_msg_id(), bad_body)])
        incoming: asyncio.Queue[ReceivedMessage | ReceiverTerminated | UpdatesRecoveryRequired] = (
            asyncio.Queue()
        )
        sender = MtprotoEncryptedSender(
            transport,
            state=_FakeState(),
            msg_id_gen=_FakeMsgIdGen(),
            incoming_queue=incoming,
        )

        task = asyncio.create_task(sender._recv_loop())
        try:
            signal = await asyncio.wait_for(incoming.get(), timeout=1.0)
            assert isinstance(signal, ReceiverTerminated)
            assert signal.requires_reconnect is True
            assert signal.constructor_id == 0x12345678
            assert signal.path == "root"
            assert transport.sent == []
            assert sender.is_healthy is False
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    asyncio.run(run())


def test_updates_loop_recovers_after_idle_interval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        recovered = asyncio.Event()
        calls: list[Any] = []

        async def invoke(req: Any) -> Any:
            calls.append(req)
            recovered.set()
            return UpdatesDifferenceEmpty(date=200, seq=4)

        monkeypatch.setattr(mtproto_module, "_UPDATES_IDLE_RECOVERY_SECONDS", 0.01)
        client = MtprotoClient()
        engine = UpdatesEngine(invoke_api=invoke)
        engine.state = UpdatesState(pts=10, qts=0, date=100, seq=3)
        client._incoming = asyncio.Queue()
        client._updates_out = asyncio.Queue()
        client._updates_engine = engine
        client._updates_terminal = asyncio.get_running_loop().create_future()
        client._updates_task = asyncio.create_task(client._updates_loop())

        await asyncio.wait_for(recovered.wait(), timeout=1.0)
        await client.stop_updates()

        assert calls
        assert isinstance(calls[0], UpdatesGetDifference)
        assert engine.state == UpdatesState(pts=10, qts=0, date=200, seq=4)

    asyncio.run(run())


def test_updates_loop_consumes_sender_recovery_signal() -> None:
    async def run() -> None:
        recovered = asyncio.Event()
        calls: list[Any] = []

        async def invoke(req: Any) -> Any:
            calls.append(req)
            recovered.set()
            return UpdatesDifferenceEmpty(date=200, seq=4)

        client = MtprotoClient()
        engine = UpdatesEngine(invoke_api=invoke)
        engine.state = UpdatesState(pts=10, qts=0, date=100, seq=3)
        incoming: asyncio.Queue[ReceivedMessage | ReceiverTerminated | UpdatesRecoveryRequired] = (
            asyncio.Queue()
        )
        incoming.put_nowait(UpdatesRecoveryRequired(reason="new_session_created"))
        client._incoming = incoming
        client._updates_out = asyncio.Queue()
        client._updates_engine = engine
        client._updates_terminal = asyncio.get_running_loop().create_future()
        client._updates_task = asyncio.create_task(client._updates_loop())

        await asyncio.wait_for(recovered.wait(), timeout=1.0)
        await client.stop_updates()

        assert calls
        assert isinstance(calls[0], UpdatesGetDifference)
        assert engine.state == UpdatesState(pts=10, qts=0, date=200, seq=4)

    asyncio.run(run())


def test_unknown_constructor_recovery_reconnects_before_get_difference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        order: list[str] = []

        async def invoke(req: Any) -> Any:
            assert isinstance(req, UpdatesGetDifference)
            order.append("get_difference")
            return UpdatesDifferenceEmpty(date=200, seq=4)

        client = MtprotoClient(init=ClientInit(api_id=123))
        engine = UpdatesEngine(invoke_api=invoke)
        engine.state = UpdatesState(pts=10, qts=0, date=100, seq=3, channel_pts={99: 7})
        incoming: asyncio.Queue[ReceivedMessage | ReceiverTerminated | UpdatesRecoveryRequired] = (
            asyncio.Queue()
        )
        incoming.put_nowait(
            UpdatesRecoveryRequired(
                reason="unknown_constructor",
                requires_reconnect=True,
                constructor_id=_LAYER_216_MESSAGE_CONSTRUCTOR_ID,
                expected_type="Message",
                path="root.updates[0].message",
                position=128,
            )
        )
        client._incoming = incoming
        client._updates_out = asyncio.Queue()
        client._updates_engine = engine
        client._updates_terminal = asyncio.get_running_loop().create_future()

        async def reconnect(*, timeout: float, poisoned_sender: Any = None) -> None:
            _ = poisoned_sender
            assert timeout > 0
            order.append("reconnect_and_init_layer")

        monkeypatch.setattr(client, "_reconnect_for_unknown_constructor", reconnect)
        monkeypatch.setattr(
            mtproto_module,
            "_UNKNOWN_CONSTRUCTOR_RECOVERY_INITIAL_BACKOFF_SECONDS",
            0.0,
        )
        client._updates_task = asyncio.create_task(client._updates_loop())

        for _ in range(100):
            if order == ["reconnect_and_init_layer", "get_difference"]:
                break
            await asyncio.sleep(0)
        await client.stop_updates()

        assert order == ["reconnect_and_init_layer", "get_difference"]
        assert engine.state == UpdatesState(
            pts=10,
            qts=0,
            date=200,
            seq=4,
            channel_pts={99: 7},
        )
        assert client._unknown_constructor_repeat_count == 1
        assert client._unknown_constructor_reconnect_attempt_count == 1

    asyncio.run(run())


def test_unknown_constructor_replacement_reuses_auth_but_creates_new_session_and_layer_init(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        order: list[str] = []

        class OldSender:
            def invalidate(self, error: Any = None) -> Any:
                order.append("old_sender_invalidate")
                return error

            async def close(self) -> None:
                order.append("old_sender_close")

        class OldTransport:
            async def close(self) -> None:
                order.append("old_transport_close")

        class CandidateTransport:
            instances: list[CandidateTransport] = []

            def __init__(self, *, endpoint: Any, framing: Any) -> None:
                self.endpoint = endpoint
                self.framing = framing
                self.closed = False
                self.instances.append(self)

            async def connect(self) -> None:
                assert "old_sender_close" in order
                assert "old_transport_close" in order
                order.append("new_tcp_connect")

            async def close(self) -> None:
                self.closed = True

        class CandidateSender:
            instances: list[CandidateSender] = []

            def __init__(
                self,
                transport: Any,
                *,
                state: Any,
                msg_id_gen: Any,
                incoming_queue: Any,
                flood_wait_config: Any,
            ) -> None:
                self.transport = transport
                self.state = state
                self.msg_id_gen = msg_id_gen
                self.incoming_queue = incoming_queue
                self.flood_wait_config = flood_wait_config
                self.closed = False
                self.instances.append(self)

            @property
            def is_healthy(self) -> bool:
                return not self.closed

            async def invoke_tl(
                self,
                request: Any,
                *,
                timeout: float,
                flood_wait_config: Any,
            ) -> Any:
                assert timeout > 0
                assert flood_wait_config is self.flood_wait_config
                assert isinstance(request, InvokeWithLayer)
                assert isinstance(request.query, InitConnection)
                assert isinstance(request.query.query, HelpGetConfig)
                order.append("invoke_with_layer_init")
                return SimpleNamespace(dc_options=[])

            async def close(self) -> None:
                self.closed = True

            def invalidate(self, error: Any = None) -> Any:
                self.closed = True
                return error

        monkeypatch.setattr(mtproto_module, "TcpTransport", CandidateTransport)
        monkeypatch.setattr(mtproto_module, "MtprotoEncryptedSender", CandidateSender)

        msg_id_gen = mtproto_module.MsgIdGenerator(server_time=time.time())
        old_state = mtproto_module.MtprotoState(
            auth_key=b"\x11" * 256,
            server_salt=b"\x22" * 8,
            msg_id_gen=msg_id_gen,
            session_id=b"old-sess",
        )
        client = MtprotoClient(
            host="149.154.167.51",
            init=ClientInit(api_id=123),
        )
        old_sender = OldSender()
        old_transport = OldTransport()
        client._sender = old_sender  # type: ignore[assignment]
        client._transport = old_transport  # type: ignore[assignment]
        client._state = old_state
        client._msg_id_gen = msg_id_gen
        client._incoming = asyncio.Queue()

        await client._reconnect_for_unknown_constructor(timeout=1.0)

        assert order[0] == "old_sender_invalidate"
        assert set(order[1:3]) == {"old_sender_close", "old_transport_close"}
        assert order[3:] == ["new_tcp_connect", "invoke_with_layer_init"]
        assert client._state is not None
        assert client._state is not old_state
        assert client._state.auth_key == old_state.auth_key
        assert client._state.server_salt == old_state.server_salt
        assert client._state.session_id != old_state.session_id
        assert client._msg_id_gen is msg_id_gen
        assert client._sender is CandidateSender.instances[0]
        assert client._transport is CandidateTransport.instances[0]
        assert client._incoming is CandidateSender.instances[0].incoming_queue
        assert client._did_init_connection is True

    asyncio.run(run())


def test_reconnect_poison_and_transport_close_release_active_invocation_before_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        order: list[str] = []
        client = MtprotoClient(host="149.154.167.51", init=ClientInit(api_id=123))

        class OldSender:
            def invalidate(self, error: Any = None) -> Any:
                order.append("invalidate")
                return error

            async def close(self) -> None:
                order.append("sender_close")

        class BlockingSendTransport:
            async def close(self) -> None:
                order.append("transport_close")
                async with client._invoke_condition:
                    client._active_invocations = 0
                    client._invoke_condition.notify_all()

        msg_id_gen = mtproto_module.MsgIdGenerator(server_time=time.time())
        client._sender = OldSender()  # type: ignore[assignment]
        client._transport = BlockingSendTransport()  # type: ignore[assignment]
        client._state = mtproto_module.MtprotoState(
            auth_key=b"\x11" * 256,
            server_salt=b"\x22" * 8,
            msg_id_gen=msg_id_gen,
        )
        client._msg_id_gen = msg_id_gen
        client._active_invocations = 1

        async def perform(*, snapshot: Any, timeout: float) -> None:
            _ = snapshot
            assert timeout > 0
            assert order[0] == "invalidate"
            assert "transport_close" in order
            assert client._active_invocations == 0
            order.append("candidate_connect")

        monkeypatch.setattr(client, "_perform_unknown_constructor_reconnect", perform)
        await client._reconnect_for_unknown_constructor(timeout=1.0)

        assert order.index("transport_close") < order.index("candidate_connect")

    asyncio.run(run())


def test_hanging_old_close_does_not_consume_candidate_connect_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        close_started = asyncio.Event()
        release_close = asyncio.Event()
        candidate_started = asyncio.Event()
        client = MtprotoClient(host="149.154.167.51", init=ClientInit(api_id=123))

        class HangingSender:
            def invalidate(self, error: Any = None) -> Any:
                return error

            async def close(self) -> None:
                close_started.set()
                await release_close.wait()

        class HangingTransport:
            async def close(self) -> None:
                close_started.set()
                await release_close.wait()

        msg_id_gen = mtproto_module.MsgIdGenerator(server_time=time.time())
        client._sender = HangingSender()  # type: ignore[assignment]
        client._transport = HangingTransport()  # type: ignore[assignment]
        client._state = mtproto_module.MtprotoState(
            auth_key=b"\x11" * 256,
            server_salt=b"\x22" * 8,
            msg_id_gen=msg_id_gen,
        )
        client._msg_id_gen = msg_id_gen

        async def perform(*, snapshot: Any, timeout: float) -> None:
            _ = snapshot
            assert close_started.is_set()
            assert timeout > 0.15
            candidate_started.set()

        monkeypatch.setattr(client, "_perform_unknown_constructor_reconnect", perform)
        try:
            await asyncio.wait_for(
                client._reconnect_for_unknown_constructor(timeout=0.25),
                timeout=0.1,
            )
            assert candidate_started.is_set()
        finally:
            release_close.set()
            await asyncio.sleep(0)

    asyncio.run(run())


def test_candidate_connect_timeout_is_hard_bounded_and_never_adopts_late(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        release_connect = asyncio.Event()
        late_connect_completed = asyncio.Event()
        final_cleanup_completed = asyncio.Event()

        class StubbornConnectTransport:
            instances: list[StubbornConnectTransport] = []

            def __init__(self, *, endpoint: Any, framing: Any) -> None:
                self.endpoint = endpoint
                self.framing = framing
                self.is_open = False
                self.close_calls = 0
                self.instances.append(self)

            async def connect(self) -> None:
                try:
                    await release_connect.wait()
                except asyncio.CancelledError:
                    # This is exactly what makes asyncio.wait_for exceed its bound.
                    await release_connect.wait()
                # Model a cancellation-suppressing connector that installs its
                # writer only after the first close tried to tear it down.
                self.is_open = True
                late_connect_completed.set()

            async def close(self) -> None:
                self.close_calls += 1
                self.is_open = False
                if self.close_calls == 1:
                    release_connect.set()
                else:
                    final_cleanup_completed.set()

        class UnexpectedSender:
            def __init__(self, *_args: Any, **_kwargs: Any) -> None:
                raise AssertionError("sender must not be built after connect deadline")

        monkeypatch.setattr(mtproto_module, "TcpTransport", StubbornConnectTransport)
        monkeypatch.setattr(mtproto_module, "MtprotoEncryptedSender", UnexpectedSender)
        client = MtprotoClient(init=ClientInit(api_id=123))
        old_sender = SimpleNamespace(name="old")
        old_transport = SimpleNamespace(name="old")
        client._sender = old_sender  # type: ignore[assignment]
        client._transport = old_transport  # type: ignore[assignment]
        snapshot = mtproto_module._UnknownConstructorReconnectSnapshot(
            sender=old_sender,
            transport=old_transport,
            auth_key=b"\x11" * 256,
            server_salt=b"\x22" * 8,
            msg_id_gen=mtproto_module.MsgIdGenerator(server_time=time.time()),
            host="149.154.167.51",
            port=443,
            framing=mtproto_module.IntermediateFraming(),
        )
        started = asyncio.get_running_loop().time()
        with pytest.raises(asyncio.TimeoutError):
            await client._perform_unknown_constructor_reconnect(
                snapshot=snapshot,
                timeout=0.02,
            )
        elapsed = asyncio.get_running_loop().time() - started

        await asyncio.wait_for(late_connect_completed.wait(), timeout=0.2)
        await asyncio.wait_for(final_cleanup_completed.wait(), timeout=0.2)
        candidate = StubbornConnectTransport.instances[0]
        assert elapsed < 0.1
        assert candidate.close_calls >= 2
        assert candidate.is_open is False
        assert client._sender is old_sender
        assert client._transport is old_transport

    asyncio.run(run())


def test_candidate_bootstrap_timeout_closes_transport_and_never_adopts_late(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        release_bootstrap = asyncio.Event()
        first_close_called = asyncio.Event()
        final_close_called = asyncio.Event()

        class CandidateTransport:
            instances: list[CandidateTransport] = []

            def __init__(self, *, endpoint: Any, framing: Any) -> None:
                self.endpoint = endpoint
                self.framing = framing
                self.close_calls = 0
                self.instances.append(self)

            async def connect(self) -> None:
                return None

            async def close(self) -> None:
                self.close_calls += 1
                if self.close_calls == 1:
                    first_close_called.set()
                    release_bootstrap.set()
                else:
                    final_close_called.set()

        class StubbornBootstrapSender:
            def __init__(self, *_args: Any, **_kwargs: Any) -> None:
                self.invalidated = False

            def invalidate(self, error: Any = None) -> Any:
                self.invalidated = True
                return error

            async def invoke_tl(self, *_args: Any, **_kwargs: Any) -> Any:
                try:
                    await release_bootstrap.wait()
                except asyncio.CancelledError:
                    await release_bootstrap.wait()
                return SimpleNamespace(dc_options=[])

            async def close(self) -> None:
                return None

        monkeypatch.setattr(mtproto_module, "TcpTransport", CandidateTransport)
        monkeypatch.setattr(mtproto_module, "MtprotoEncryptedSender", StubbornBootstrapSender)
        client = MtprotoClient(init=ClientInit(api_id=123))
        old_sender = SimpleNamespace(name="old")
        old_transport = SimpleNamespace(name="old")
        client._sender = old_sender  # type: ignore[assignment]
        client._transport = old_transport  # type: ignore[assignment]
        snapshot = mtproto_module._UnknownConstructorReconnectSnapshot(
            sender=old_sender,
            transport=old_transport,
            auth_key=b"\x11" * 256,
            server_salt=b"\x22" * 8,
            msg_id_gen=mtproto_module.MsgIdGenerator(server_time=time.time()),
            host="149.154.167.51",
            port=443,
            framing=mtproto_module.IntermediateFraming(),
        )
        started = asyncio.get_running_loop().time()
        with pytest.raises(asyncio.TimeoutError):
            await client._perform_unknown_constructor_reconnect(
                snapshot=snapshot,
                timeout=0.02,
            )
        elapsed = asyncio.get_running_loop().time() - started

        await asyncio.wait_for(first_close_called.wait(), timeout=0.2)
        await asyncio.wait_for(final_close_called.wait(), timeout=0.2)
        assert CandidateTransport.instances[0].close_calls >= 2
        assert elapsed < 0.1
        assert client._sender is old_sender
        assert client._transport is old_transport

    asyncio.run(run())


def test_repeated_unknown_constructor_opens_circuit_and_preserves_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        reconnects = 0
        initial = UpdatesState(
            pts=10,
            qts=2,
            date=100,
            seq=3,
            channel_pts={99: 7},
        )

        async def invoke(_req: Any) -> Any:
            raise RpcDecodeError(
                "same legacy message",
                constructor_id=_LAYER_216_MESSAGE_CONSTRUCTOR_ID,
                expected_type="Message",
                path="root.rpc_result.new_messages[0]",
                position=64,
                requires_reconnect=True,
            )

        client = MtprotoClient(init=ClientInit(api_id=123))
        engine = UpdatesEngine(invoke_api=invoke)
        engine.state = UpdatesState(
            pts=initial.pts,
            qts=initial.qts,
            date=initial.date,
            seq=initial.seq,
            channel_pts=dict(initial.channel_pts),
        )
        incoming: asyncio.Queue[ReceivedMessage | ReceiverTerminated | UpdatesRecoveryRequired] = (
            asyncio.Queue()
        )
        incoming.put_nowait(
            UpdatesRecoveryRequired(
                reason="unknown_constructor",
                requires_reconnect=True,
                constructor_id=_LAYER_216_MESSAGE_CONSTRUCTOR_ID,
                expected_type="Message",
                path="root.rpc_result.new_messages[0]",
                position=64,
            )
        )
        client._incoming = incoming
        client._updates_out = asyncio.Queue()
        client._updates_engine = engine
        client._updates_terminal = asyncio.get_running_loop().create_future()

        async def reconnect(*, timeout: float, poisoned_sender: Any = None) -> None:
            _ = poisoned_sender
            nonlocal reconnects
            assert timeout > 0
            reconnects += 1

        monkeypatch.setattr(client, "_reconnect_for_unknown_constructor", reconnect)
        monkeypatch.setattr(
            mtproto_module,
            "_UNKNOWN_CONSTRUCTOR_RECOVERY_INITIAL_BACKOFF_SECONDS",
            0.0,
        )
        client._updates_task = asyncio.create_task(client._updates_loop())
        await asyncio.wait_for(client._updates_task, timeout=1.0)

        assert reconnects == 3
        assert engine.checkpoint() == initial
        assert client._updates_terminal is not None
        error = client._updates_terminal.result()
        assert isinstance(error, UpdatesRecoveryExhaustedError)
        assert error.constructor_id == _LAYER_216_MESSAGE_CONSTRUCTOR_ID
        assert error.path == "root.rpc_result.new_messages[0]"
        assert error.attempts == 3
        assert error.repeat_count == 4
        assert error.consecutive_failure_count == 4
        assert error.retryable is False
        client._updates_task = None

    asyncio.run(run())


def test_unknown_then_date_only_difference_episodes_cannot_loop_forever(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        reconnects = 0
        differences = 0
        initial = UpdatesState(pts=10, qts=2, date=100, seq=3, channel_pts={99: 7})

        async def invoke(_req: Any) -> Any:
            nonlocal differences
            differences += 1
            # Telegram commonly advances only date in an empty difference. That
            # is not evidence that the poisoned live envelope stopped recurring.
            return UpdatesDifferenceEmpty(
                date=initial.date + differences,
                seq=initial.seq,
            )

        signal = UpdatesRecoveryRequired(
            reason="unknown_constructor",
            requires_reconnect=True,
            constructor_id=_LAYER_216_MESSAGE_CONSTRUCTOR_ID,
            path="root.updates[0].message",
            position=64,
        )
        client = MtprotoClient(init=ClientInit(api_id=123))
        engine = UpdatesEngine(invoke_api=invoke)
        engine.state = UpdatesState(
            pts=initial.pts,
            qts=initial.qts,
            date=initial.date,
            seq=initial.seq,
            channel_pts=dict(initial.channel_pts),
        )
        incoming: asyncio.Queue[ReceivedMessage | ReceiverTerminated | UpdatesRecoveryRequired] = (
            asyncio.Queue()
        )
        for _ in range(4):
            incoming.put_nowait(signal)
        client._incoming = incoming
        client._updates_out = asyncio.Queue()
        client._updates_engine = engine
        client._updates_terminal = asyncio.get_running_loop().create_future()

        async def reconnect(*, timeout: float, poisoned_sender: Any = None) -> None:
            _ = poisoned_sender
            nonlocal reconnects
            assert timeout > 0
            reconnects += 1

        monkeypatch.setattr(client, "_reconnect_for_unknown_constructor", reconnect)
        monkeypatch.setattr(
            mtproto_module,
            "_UNKNOWN_CONSTRUCTOR_RECOVERY_INITIAL_BACKOFF_SECONDS",
            0.0,
        )
        client._updates_task = asyncio.create_task(client._updates_loop())
        await asyncio.wait_for(client._updates_task, timeout=1.0)

        assert reconnects == 3
        assert differences == 3
        assert engine.checkpoint() == UpdatesState(
            pts=initial.pts,
            qts=initial.qts,
            date=initial.date + 3,
            seq=initial.seq,
            channel_pts=dict(initial.channel_pts),
        )
        assert client._updates_terminal is not None
        error = client._updates_terminal.result()
        assert isinstance(error, UpdatesRecoveryExhaustedError)
        assert error.repeat_count == 4
        assert error.consecutive_failure_count == 4
        client._updates_task = None

    asyncio.run(run())


def test_nonempty_difference_recovery_does_not_disarm_live_poison_circuit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        reconnects = 0
        differences = 0
        initial = UpdatesState(pts=10, qts=2, date=100, seq=3)

        async def invoke(req: Any) -> Any:
            nonlocal differences
            assert isinstance(req, UpdatesGetDifference)
            differences += 1
            # A valid nonempty difference proves only that catch-up decoded; it
            # does not prove the independent live stream stopped returning the
            # same poisoned envelope.
            return UpdatesDifference(
                new_messages=[],
                new_encrypted_messages=[],
                other_updates=[SimpleNamespace(TL_NAME="syntheticRecoveredUpdate")],
                chats=[],
                users=[],
                state=_tl_state(
                    pts=int(req.pts) + 1,
                    qts=int(req.qts),
                    date=int(req.date) + 1,
                    seq=initial.seq + differences,
                ),
            )

        signal = UpdatesRecoveryRequired(
            reason="unknown_constructor",
            requires_reconnect=True,
            constructor_id=_LAYER_216_MESSAGE_CONSTRUCTOR_ID,
            path="root.updates[0].message",
            position=64,
        )
        client = MtprotoClient(init=ClientInit(api_id=123))
        engine = UpdatesEngine(invoke_api=invoke)
        engine.state = initial
        incoming: asyncio.Queue[ReceivedMessage | ReceiverTerminated | UpdatesRecoveryRequired] = (
            asyncio.Queue()
        )
        for _ in range(4):
            incoming.put_nowait(signal)
        client._incoming = incoming
        client._updates_out = asyncio.Queue()
        client._updates_engine = engine
        client._updates_terminal = asyncio.get_running_loop().create_future()

        async def reconnect(*, timeout: float, poisoned_sender: Any = None) -> None:
            _ = poisoned_sender
            nonlocal reconnects
            assert timeout > 0
            reconnects += 1

        monkeypatch.setattr(client, "_reconnect_for_unknown_constructor", reconnect)
        monkeypatch.setattr(
            mtproto_module,
            "_UNKNOWN_CONSTRUCTOR_RECOVERY_INITIAL_BACKOFF_SECONDS",
            0.0,
        )
        client._updates_task = asyncio.create_task(client._updates_loop())
        await asyncio.wait_for(client._updates_task, timeout=1.0)

        assert reconnects == 3
        assert differences == 3
        assert engine.checkpoint().pts == initial.pts + 3
        assert client._updates_out.qsize() == 3
        assert client._updates_terminal is not None
        error = client._updates_terminal.result()
        assert isinstance(error, UpdatesRecoveryExhaustedError)
        assert error.attempts == 3
        assert error.repeat_count == 4
        assert error.consecutive_failure_count == 4
        client._updates_task = None

    asyncio.run(run())


def test_delivered_live_payload_with_cursor_progress_disarms_poison_circuit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        reconnects = 0

        async def invoke(req: Any) -> Any:
            assert isinstance(req, UpdatesGetDifference)
            return UpdatesDifferenceEmpty(date=100, seq=3)

        client = MtprotoClient(init=ClientInit(api_id=123))
        engine = UpdatesEngine(invoke_api=invoke)
        engine.state = UpdatesState(pts=10, qts=0, date=100, seq=3)
        live_update = SimpleNamespace(
            TL_NAME="updateNewMessage",
            pts=11,
            pts_count=1,
        )
        incoming: asyncio.Queue[ReceivedMessage | ReceiverTerminated | UpdatesRecoveryRequired] = (
            asyncio.Queue()
        )
        incoming.put_nowait(
            UpdatesRecoveryRequired(
                reason="unknown_constructor",
                requires_reconnect=True,
                constructor_id=_LAYER_216_MESSAGE_CONSTRUCTOR_ID,
                path="root.updates[0].message",
                position=64,
            )
        )
        incoming.put_nowait(
            ReceivedMessage(
                msg_id=1,
                seqno=1,
                obj=UpdateShort(update=live_update, date=101),
            )
        )
        client._incoming = incoming
        client._updates_out = asyncio.Queue()
        client._updates_engine = engine
        client._updates_terminal = asyncio.get_running_loop().create_future()

        async def reconnect(*, timeout: float, poisoned_sender: Any = None) -> None:
            _ = poisoned_sender
            nonlocal reconnects
            assert timeout > 0
            reconnects += 1

        monkeypatch.setattr(client, "_reconnect_for_unknown_constructor", reconnect)
        monkeypatch.setattr(
            mtproto_module,
            "_UNKNOWN_CONSTRUCTOR_RECOVERY_INITIAL_BACKOFF_SECONDS",
            0.0,
        )
        client._updates_task = asyncio.create_task(client._updates_loop())

        for _ in range(100):
            if client._updates_out.qsize() == 1:
                break
            await asyncio.sleep(0)

        assert reconnects == 1
        assert engine.checkpoint().pts == 11
        assert client._updates_out.get_nowait() is live_update
        assert client._unknown_constructor_fingerprint is None
        assert client._unknown_constructor_repeat_count == 0
        assert client._unknown_constructor_consecutive_failure_count == 0
        assert client._unknown_constructor_reconnect_attempt_count == 0
        await client.stop_updates()

    asyncio.run(run())


def test_alternating_unknown_fingerprints_cannot_bypass_global_circuit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        reconnects = 0
        initial = UpdatesState(pts=10, qts=2, date=100, seq=3)

        async def invoke(_req: Any) -> Any:
            return UpdatesDifferenceEmpty(date=initial.date, seq=initial.seq)

        client = MtprotoClient(init=ClientInit(api_id=123))
        engine = UpdatesEngine(invoke_api=invoke)
        engine.state = initial
        incoming: asyncio.Queue[ReceivedMessage | ReceiverTerminated | UpdatesRecoveryRequired] = (
            asyncio.Queue()
        )
        for constructor_id, path in (
            (1, "root.a"),
            (2, "root.b"),
            (1, "root.a"),
            (2, "root.b"),
        ):
            incoming.put_nowait(
                UpdatesRecoveryRequired(
                    reason="unknown_constructor",
                    requires_reconnect=True,
                    constructor_id=constructor_id,
                    path=path,
                    position=4,
                )
            )
        client._incoming = incoming
        client._updates_out = asyncio.Queue()
        client._updates_engine = engine
        client._updates_terminal = asyncio.get_running_loop().create_future()

        async def reconnect(*, timeout: float, poisoned_sender: Any = None) -> None:
            _ = poisoned_sender
            nonlocal reconnects
            assert timeout > 0
            reconnects += 1

        monkeypatch.setattr(client, "_reconnect_for_unknown_constructor", reconnect)
        monkeypatch.setattr(
            mtproto_module,
            "_UNKNOWN_CONSTRUCTOR_RECOVERY_INITIAL_BACKOFF_SECONDS",
            0.0,
        )
        client._updates_task = asyncio.create_task(client._updates_loop())
        await asyncio.wait_for(client._updates_task, timeout=1.0)

        assert reconnects == 3
        assert engine.checkpoint() == initial
        assert client._updates_terminal is not None
        error = client._updates_terminal.result()
        assert isinstance(error, UpdatesRecoveryExhaustedError)
        assert error.constructor_id == 2
        assert error.path == "root.b"
        assert error.repeat_count == 1
        assert error.consecutive_failure_count == 4
        client._updates_task = None

    asyncio.run(run())


def test_mixed_recovery_episodes_share_attempt_budget_and_backoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        reconnects = 0
        delays: list[float] = []
        client = MtprotoClient(init=ClientInit(api_id=123))

        async def reconnect(
            *,
            timeout: float,
            poisoned_sender: Any = None,
        ) -> None:
            nonlocal reconnects
            _ = poisoned_sender
            assert timeout > 0
            reconnects += 1

        async def record_sleep(delay: float) -> None:
            delays.append(delay)

        async def empty_success() -> bool:
            return False

        monkeypatch.setattr(client, "_reconnect_for_unknown_constructor", reconnect)
        monkeypatch.setattr(mtproto_module.asyncio, "sleep", record_sleep)

        signals = [
            UpdatesRecoveryRequired(
                reason="unknown_constructor",
                requires_reconnect=True,
                constructor_id=constructor_id,
                path=path,
                position=4,
            )
            for constructor_id, path in (
                (1, "root.a"),
                (2, "root.b"),
                (1, "root.a"),
                (2, "root.b"),
            )
        ]
        for signal in signals[:3]:
            assert (
                await client._run_after_unknown_constructor(
                    signal,
                    operation=empty_success,
                    restore_checkpoint=None,
                    timeout=1.0,
                )
                is False
            )

        with pytest.raises(UpdatesRecoveryExhaustedError):
            await client._run_after_unknown_constructor(
                signals[3],
                operation=empty_success,
                restore_checkpoint=None,
                timeout=1.0,
            )

        assert reconnects == 3
        assert delays == [0.25, 0.5]

    asyncio.run(run())


def test_start_updates_recovers_poisoned_initial_difference_transactionally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        calls = 0
        reconnects = 0
        durable = UpdatesState(pts=10, qts=2, date=100, seq=3, channel_pts={7: 9})
        client = MtprotoClient(init=ClientInit(api_id=123))
        client._incoming = asyncio.Queue()
        monkeypatch.setattr(client, "_load_updates_state", lambda: durable)

        async def invoke_api(req: Any, *, timeout: float = 20.0) -> Any:
            nonlocal calls
            assert timeout > 0
            assert isinstance(req, UpdatesGetDifference)
            calls += 1
            if calls == 1:
                raise RpcDecodeError(
                    "legacy startup response",
                    constructor_id=_LAYER_216_MESSAGE_CONSTRUCTOR_ID,
                    path="root.rpc_result.new_messages[0]",
                    position=64,
                    requires_reconnect=True,
                )
            assert int(req.pts) == durable.pts
            assert int(req.qts) == durable.qts
            assert int(req.date) == durable.date
            return UpdatesDifferenceEmpty(date=200, seq=4)

        async def reconnect(*, timeout: float, poisoned_sender: Any = None) -> None:
            _ = poisoned_sender
            nonlocal reconnects
            assert timeout > 0
            reconnects += 1

        monkeypatch.setattr(client, "invoke_api", invoke_api)
        monkeypatch.setattr(client, "_reconnect_for_unknown_constructor", reconnect)
        monkeypatch.setattr(
            mtproto_module,
            "_UNKNOWN_CONSTRUCTOR_RECOVERY_INITIAL_BACKOFF_SECONDS",
            0.0,
        )

        await client.start_updates(timeout=1.0)
        assert calls == 2
        assert reconnects == 1
        assert client._updates_engine is not None
        assert client._updates_engine.checkpoint() == UpdatesState(
            pts=10,
            qts=2,
            date=200,
            seq=4,
            channel_pts={7: 9},
        )
        await client.stop_updates()

    asyncio.run(run())


def test_startup_date_only_recovery_keeps_global_circuit_armed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        calls = 0
        reconnects = 0
        durable = UpdatesState(pts=10, qts=2, date=100, seq=3)
        client = MtprotoClient(init=ClientInit(api_id=123))
        client._incoming = asyncio.Queue()
        monkeypatch.setattr(client, "_load_updates_state", lambda: durable)

        async def invoke_api(req: Any, *, timeout: float = 20.0) -> Any:
            nonlocal calls
            assert timeout > 0
            assert isinstance(req, UpdatesGetDifference)
            calls += 1
            if calls == 1:
                raise RpcDecodeError(
                    "startup poison",
                    constructor_id=1,
                    path="root.a",
                    position=4,
                    requires_reconnect=True,
                )
            return UpdatesDifferenceEmpty(date=100 + calls, seq=durable.seq)

        async def reconnect(
            *,
            timeout: float,
            poisoned_sender: Any = None,
        ) -> None:
            nonlocal reconnects
            _ = poisoned_sender
            assert timeout > 0
            reconnects += 1

        monkeypatch.setattr(client, "invoke_api", invoke_api)
        monkeypatch.setattr(client, "_reconnect_for_unknown_constructor", reconnect)
        monkeypatch.setattr(
            mtproto_module,
            "_UNKNOWN_CONSTRUCTOR_RECOVERY_INITIAL_BACKOFF_SECONDS",
            0.0,
        )

        await client.start_updates(timeout=1.0)
        assert reconnects == 1
        assert client._unknown_constructor_consecutive_failure_count == 1
        assert client._incoming is not None
        for constructor_id, path in ((2, "root.b"), (1, "root.a"), (2, "root.b")):
            client._incoming.put_nowait(
                UpdatesRecoveryRequired(
                    reason="unknown_constructor",
                    requires_reconnect=True,
                    constructor_id=constructor_id,
                    path=path,
                    position=4,
                )
            )

        assert client._updates_task is not None
        await asyncio.wait_for(client._updates_task, timeout=1.0)
        assert reconnects == 3
        assert calls == 4
        assert client._updates_terminal is not None
        error = client._updates_terminal.result()
        assert isinstance(error, UpdatesRecoveryExhaustedError)
        assert error.consecutive_failure_count == 4
        client._updates_task = None

    asyncio.run(run())
