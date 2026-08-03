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
from telecraft.client.mtproto import MtprotoClient
from telecraft.mtproto.rpc.sender import (
    MtprotoEncryptedSender,
    ReceivedMessage,
    ReceiverTerminated,
    UpdatesRecoveryRequired,
)
from telecraft.mtproto.updates.engine import UpdatesEngine, UpdatesEngineError
from telecraft.mtproto.updates.state import UpdatesState
from telecraft.tl.generated.functions import (
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
            assert signal == UpdatesRecoveryRequired(reason="tl_decode_failure")
            assert len(transport.sent) == 1
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
