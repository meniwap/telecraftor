from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from telecraft.mtproto.updates.engine import UpdatesEngine
from telecraft.mtproto.updates.state import UpdatesState
from telecraft.tl.generated.functions import UpdatesGetDifference
from telecraft.tl.generated.types import (
    InputChannel,
    UpdateChannelTooLong,
    Updates,
    UpdatesChannelDifference,
    UpdatesChannelDifferenceEmpty,
    UpdatesCombined,
    UpdatesDifference,
    UpdateShort,
)
from telecraft.tl.generated.types import (
    UpdatesState as TlUpdatesState,
)


def _difference(*, update: Any, pts: int, date: int, seq: int) -> UpdatesDifference:
    return UpdatesDifference(
        new_messages=[],
        new_encrypted_messages=[],
        other_updates=[update],
        chats=[],
        users=[],
        state=TlUpdatesState(pts=pts, qts=0, date=date, seq=seq, unread_count=0),
    )


@pytest.mark.parametrize(
    "envelope",
    [
        Updates(updates=[], users=[], chats=[], date=200, seq=7),
        UpdatesCombined(
            updates=[], users=[], chats=[], date=200, seq_start=7, seq=8
        ),
    ],
)
def test_seq_gap_recovers_without_emitting_discontinuous_envelope(envelope: Any) -> None:
    incoming = SimpleNamespace(TL_NAME="updateIncoming")
    envelope.updates = [incoming]
    recovered = SimpleNamespace(TL_NAME="updateRecovered")
    calls: list[Any] = []

    async def invoke(req: Any) -> Any:
        calls.append(req)
        assert engine.state == UpdatesState(pts=10, qts=0, date=100, seq=5)
        return _difference(update=recovered, pts=11, date=150, seq=6)

    engine = UpdatesEngine(invoke_api=invoke)
    engine.state = UpdatesState(pts=10, qts=0, date=100, seq=5)

    applied = asyncio.run(engine.apply(envelope))

    assert len(calls) == 1
    assert isinstance(calls[0], UpdatesGetDifference)
    assert calls[0].pts == 10
    assert calls[0].date == 100
    assert applied.updates == [recovered]
    assert incoming not in applied.updates
    assert engine.state == UpdatesState(pts=11, qts=0, date=150, seq=6)


def test_stale_seq_envelope_is_dropped_without_network_or_state_change() -> None:
    async def invoke(_req: Any) -> Any:
        raise AssertionError("stale envelope must not trigger a network request")

    engine = UpdatesEngine(invoke_api=invoke)
    engine.state = UpdatesState(pts=10, qts=0, date=100, seq=5)
    incoming = SimpleNamespace(TL_NAME="updateDuplicate")
    envelope = Updates(updates=[incoming], users=[], chats=[], date=200, seq=5)

    applied = asyncio.run(engine.apply(envelope))

    assert applied.updates == []
    assert engine.state == UpdatesState(pts=10, qts=0, date=100, seq=5)


def test_pts_mismatch_does_not_emit_or_advance_envelope_before_recovery() -> None:
    incoming = SimpleNamespace(TL_NAME="updateIncoming", pts=12, pts_count=1)
    recovered = SimpleNamespace(TL_NAME="updateRecovered")
    observed_states: list[UpdatesState] = []

    async def invoke(req: Any) -> Any:
        assert isinstance(req, UpdatesGetDifference)
        observed_states.append(engine.checkpoint())
        return _difference(update=recovered, pts=12, date=175, seq=6)

    engine = UpdatesEngine(invoke_api=invoke)
    engine.state = UpdatesState(pts=10, qts=0, date=100, seq=5)
    envelope = Updates(updates=[incoming], users=[], chats=[], date=200, seq=6)

    applied = asyncio.run(engine.apply(envelope))

    assert observed_states == [UpdatesState(pts=10, qts=0, date=100, seq=5)]
    assert applied.updates == [recovered]
    assert incoming not in applied.updates
    assert engine.state == UpdatesState(pts=12, qts=0, date=175, seq=6)


def test_update_short_does_not_advance_date_on_inner_pts_mismatch() -> None:
    incoming = SimpleNamespace(TL_NAME="updateIncoming", pts=12, pts_count=1)
    recovered = SimpleNamespace(TL_NAME="updateRecovered")

    async def invoke(_req: Any) -> Any:
        assert engine.state == UpdatesState(pts=10, qts=0, date=100, seq=5)
        return _difference(update=recovered, pts=12, date=175, seq=6)

    engine = UpdatesEngine(invoke_api=invoke)
    engine.state = UpdatesState(pts=10, qts=0, date=100, seq=5)

    applied = asyncio.run(engine.apply(UpdateShort(update=incoming, date=200)))

    assert applied.updates == [recovered]
    assert engine.state == UpdatesState(pts=12, qts=0, date=175, seq=6)


def test_contiguous_batch_commits_counters_and_envelope_together() -> None:
    first = SimpleNamespace(TL_NAME="updateFirst", pts=11, pts_count=1)
    second = SimpleNamespace(TL_NAME="updateSecond", pts=13, pts_count=2)

    async def invoke(_req: Any) -> Any:
        raise AssertionError("contiguous updates must not recover")

    engine = UpdatesEngine(invoke_api=invoke)
    engine.state = UpdatesState(pts=10, qts=0, date=100, seq=5)
    envelope = Updates(updates=[first, second], users=[], chats=[], date=200, seq=6)

    applied = asyncio.run(engine.apply(envelope))

    assert applied.updates == [first, second]
    assert engine.state == UpdatesState(pts=13, qts=0, date=200, seq=6)


def test_persisted_state_is_caught_up_and_offline_updates_are_replayable() -> None:
    offline_update = SimpleNamespace(TL_NAME="updateWhileOffline")
    persisted = UpdatesState(pts=10, qts=0, date=100, seq=5)
    calls: list[Any] = []

    async def invoke(req: Any) -> Any:
        calls.append(req)
        return _difference(update=offline_update, pts=11, date=150, seq=6)

    engine = UpdatesEngine(invoke_api=invoke)
    state = asyncio.run(engine.initialize(initial_state=persisted))
    catch_up = engine.take_initial_catch_up()

    assert len(calls) == 1
    assert isinstance(calls[0], UpdatesGetDifference)
    assert calls[0].pts == 10
    assert state == UpdatesState(pts=11, qts=0, date=150, seq=6)
    assert persisted == UpdatesState(pts=10, qts=0, date=100, seq=5)
    assert catch_up is not None
    checkpoint, applied = catch_up
    assert checkpoint == persisted
    assert applied.updates == [offline_update]
    assert engine.take_initial_catch_up() is None


def test_fresh_pts_update_is_applied_even_when_envelope_seq_is_stale() -> None:
    async def invoke(_req: Any) -> Any:
        raise AssertionError("a fresh pts update must not be discarded with stale seq data")

    engine = UpdatesEngine(invoke_api=invoke)
    engine.state = UpdatesState(pts=10, qts=0, date=100, seq=5)
    message_update = SimpleNamespace(TL_NAME="updateNewMessage", pts=11, pts_count=1)
    envelope = Updates(
        updates=[message_update],
        users=[],
        chats=[],
        date=200,
        seq=5,
    )

    applied = asyncio.run(engine.apply(envelope))

    assert applied.updates == [message_update]
    assert engine.state == UpdatesState(pts=11, qts=0, date=100, seq=5)


def test_stale_qts_update_is_ignored_without_duplicate_delivery() -> None:
    async def invoke(_req: Any) -> Any:
        raise AssertionError("a stale qts update must not trigger recovery")

    engine = UpdatesEngine(invoke_api=invoke)
    engine.state = UpdatesState(pts=10, qts=5, date=100, seq=5)
    duplicate = SimpleNamespace(TL_NAME="updateEncryptedMessagesRead", qts=5)

    applied = asyncio.run(engine.apply(duplicate))

    assert applied.updates == []
    assert engine.state == UpdatesState(pts=10, qts=5, date=100, seq=5)


def test_seq_start_zero_is_applied_as_an_unordered_envelope() -> None:
    async def invoke(_req: Any) -> Any:
        raise AssertionError("seq_start=0 must not trigger updates.getDifference")

    engine = UpdatesEngine(invoke_api=invoke)
    engine.state = UpdatesState(pts=10, qts=0, date=100, seq=5)
    unordered = SimpleNamespace(TL_NAME="updateConfig")
    envelope = UpdatesCombined(
        updates=[unordered],
        users=[],
        chats=[],
        date=200,
        seq_start=0,
        seq=6,
    )

    applied = asyncio.run(engine.apply(envelope))

    assert applied.updates == [unordered]
    assert engine.state == UpdatesState(pts=10, qts=0, date=200, seq=6)


def test_channel_pts_ready_duplicate_and_gap_use_independent_cursor() -> None:
    calls: list[Any] = []

    async def invoke(req: Any) -> Any:
        calls.append(req)
        return UpdatesChannelDifferenceEmpty(flags=1, final=True, pts=14, timeout=None)

    engine = UpdatesEngine(
        invoke_api=invoke,
        resolve_input_channel=lambda channel_id: InputChannel(
            channel_id=channel_id,
            access_hash=123,
        ),
    )
    engine.state = UpdatesState(pts=50, qts=0, date=100, seq=5)
    engine._channel_pts[123] = 10
    ready = SimpleNamespace(
        TL_NAME="updateDeleteChannelMessages",
        channel_id=123,
        pts=11,
        pts_count=1,
    )
    gap = SimpleNamespace(
        TL_NAME="updateDeleteChannelMessages",
        channel_id=123,
        pts=14,
        pts_count=1,
    )

    async def run() -> tuple[Any, Any, Any]:
        first = await engine.apply(ready)
        duplicate = await engine.apply(ready)
        recovered = await engine.apply(gap)
        return first, duplicate, recovered

    first, duplicate, recovered = asyncio.run(run())

    assert first.updates == [ready]
    assert duplicate.updates == []
    assert recovered.updates == []
    assert len(calls) == 1
    assert calls[0].pts == 11
    assert calls[0].force is False
    assert engine._channel_pts[123] == 14
    assert engine.state == UpdatesState(pts=50, qts=0, date=100, seq=5)


def test_channel_cursor_rolls_back_with_undelivered_difference_batch() -> None:
    request_pts: list[int] = []
    recovered_message = SimpleNamespace(TL_NAME="message", id=1)

    async def invoke(req: Any) -> Any:
        request_pts.append(int(req.pts))
        return UpdatesChannelDifference(
            flags=1,
            final=True,
            pts=5,
            timeout=None,
            new_messages=[recovered_message],
            other_updates=[],
            chats=[],
            users=[],
        )

    engine = UpdatesEngine(
        invoke_api=invoke,
        resolve_input_channel=lambda channel_id: InputChannel(
            channel_id=channel_id,
            access_hash=123,
        ),
    )
    engine.state = UpdatesState(pts=10, qts=0, date=100, seq=5)
    trigger = UpdateChannelTooLong(flags=0, channel_id=123, pts=None)

    async def run() -> tuple[Any, Any]:
        checkpoint = engine.checkpoint()
        first = await engine.apply(trigger)
        engine.restore(checkpoint)
        second = await engine.apply(trigger)
        return first, second

    first, second = asyncio.run(run())

    assert first.new_messages == [recovered_message]
    assert second.new_messages == [recovered_message]
    assert request_pts == [1, 1]
    assert engine._channel_pts[123] == 5


def test_channel_recovery_can_use_access_hash_from_same_envelope() -> None:
    requests: list[Any] = []

    async def invoke(req: Any) -> Any:
        requests.append(req)
        return UpdatesChannelDifferenceEmpty(flags=1, final=True, pts=9, timeout=None)

    engine = UpdatesEngine(invoke_api=invoke)
    engine.state = UpdatesState(pts=10, qts=0, date=100, seq=5)
    trigger = UpdateChannelTooLong(flags=0, channel_id=123, pts=None)
    channel = SimpleNamespace(TL_NAME="channel", id=123, access_hash=456)
    envelope = Updates(
        updates=[trigger],
        users=[],
        chats=[channel],
        date=200,
        seq=6,
    )

    asyncio.run(engine.apply(envelope))

    assert len(requests) == 1
    assert requests[0].channel == InputChannel(channel_id=123, access_hash=456)
    assert engine._channel_pts[123] == 9
