from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from telecraft.mtproto.rpc.sender import RpcErrorException
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


def test_channel_recovery_ignores_min_hash_and_uses_full_cached_entity() -> None:
    requests: list[Any] = []

    async def invoke(req: Any) -> Any:
        requests.append(req)
        return UpdatesChannelDifferenceEmpty(flags=1, final=True, pts=9, timeout=None)

    engine = UpdatesEngine(
        invoke_api=invoke,
        resolve_input_channel=lambda channel_id: InputChannel(
            channel_id=channel_id,
            access_hash=789,
        ),
    )
    engine.state = UpdatesState(pts=10, qts=0, date=100, seq=5)
    trigger = UpdateChannelTooLong(flags=0, channel_id=123, pts=None)
    min_channel = SimpleNamespace(
        TL_NAME="channel",
        id=123,
        access_hash=456,
        min=True,
    )
    envelope = Updates(
        updates=[trigger],
        users=[],
        chats=[min_channel],
        date=200,
        seq=6,
    )

    asyncio.run(engine.apply(envelope))

    assert len(requests) == 1
    assert requests[0].channel == InputChannel(channel_id=123, access_hash=789)


def test_unresolvable_channel_is_isolated_without_stopping_global_updates() -> None:
    async def invoke(_req: Any) -> Any:
        raise AssertionError("a channel without a full access hash cannot be queried")

    engine = UpdatesEngine(
        invoke_api=invoke,
        resolve_input_channel=lambda _channel_id: None,
    )
    engine.state = UpdatesState(pts=10, qts=0, date=100, seq=5)
    trigger = UpdateChannelTooLong(flags=0, channel_id=123, pts=None)
    envelope = Updates(
        updates=[trigger],
        users=[],
        chats=[],
        date=200,
        seq=6,
    )

    applied = asyncio.run(engine.apply(envelope))

    assert applied.updates == []
    assert applied.new_messages == []
    assert engine.state == UpdatesState(pts=10, qts=0, date=200, seq=6)
    assert 123 not in engine._channel_pts


@pytest.mark.parametrize(
    "error_message",
    ["CHANNEL_INVALID", "CHANNEL_PRIVATE", "CHANNEL_PUBLIC_GROUP_NA"],
)
def test_permanently_unavailable_channel_error_is_isolated(error_message: str) -> None:
    async def invoke(_req: Any) -> Any:
        raise RpcErrorException(code=400, message=error_message)

    engine = UpdatesEngine(
        invoke_api=invoke,
        resolve_input_channel=lambda channel_id: InputChannel(
            channel_id=channel_id,
            access_hash=789,
        ),
    )
    engine.state = UpdatesState(pts=10, qts=0, date=100, seq=5)
    engine._channel_pts[123] = 8

    applied = asyncio.run(
        engine.apply(UpdateChannelTooLong(flags=0, channel_id=123, pts=None))
    )

    assert applied.updates == []
    assert applied.new_messages == []
    assert 123 not in engine._channel_pts


def test_unavailable_channel_does_not_block_other_channel_in_same_envelope() -> None:
    async def invoke(req: Any) -> Any:
        if int(req.channel.channel_id) == 123:
            raise RpcErrorException(code=400, message="CHANNEL_PRIVATE")
        return UpdatesChannelDifferenceEmpty(flags=1, final=True, pts=12, timeout=None)

    engine = UpdatesEngine(invoke_api=invoke)
    engine.state = UpdatesState(pts=10, qts=0, date=100, seq=5)
    first = UpdateChannelTooLong(flags=0, channel_id=123, pts=None)
    second = UpdateChannelTooLong(flags=0, channel_id=456, pts=None)
    envelope = Updates(
        updates=[first, second],
        users=[],
        chats=[
            SimpleNamespace(TL_NAME="channel", id=123, access_hash=111, min=False),
            SimpleNamespace(TL_NAME="channel", id=456, access_hash=222, min=False),
        ],
        date=200,
        seq=6,
    )

    applied = asyncio.run(engine.apply(envelope))

    assert applied.updates == []
    assert 123 not in engine._channel_pts
    assert engine._channel_pts[456] == 12
    assert engine.state == UpdatesState(pts=10, qts=0, date=200, seq=6)


def test_channel_pages_are_not_partially_delivered_if_access_is_lost() -> None:
    calls = 0
    partial_message = SimpleNamespace(TL_NAME="message", id=1)

    async def invoke(_req: Any) -> Any:
        nonlocal calls
        calls += 1
        if calls == 1:
            return UpdatesChannelDifference(
                flags=0,
                final=False,
                pts=9,
                timeout=None,
                new_messages=[partial_message],
                other_updates=[],
                chats=[],
                users=[],
            )
        raise RpcErrorException(code=406, message="CHANNEL_PRIVATE")

    engine = UpdatesEngine(
        invoke_api=invoke,
        resolve_input_channel=lambda channel_id: InputChannel(
            channel_id=channel_id,
            access_hash=789,
        ),
    )
    engine.state = UpdatesState(pts=10, qts=0, date=100, seq=5)

    applied = asyncio.run(
        engine.apply(UpdateChannelTooLong(flags=0, channel_id=123, pts=None))
    )

    assert calls == 2
    assert applied.new_messages == []
    assert applied.updates == []
    assert 123 not in engine._channel_pts


def test_startup_difference_is_not_aborted_by_min_only_channel() -> None:
    trigger = UpdateChannelTooLong(flags=0, channel_id=123, pts=None)
    min_channel = SimpleNamespace(
        TL_NAME="channel",
        id=123,
        access_hash=456,
        min=True,
    )
    calls: list[Any] = []

    async def invoke(req: Any) -> Any:
        calls.append(req)
        assert isinstance(req, UpdatesGetDifference)
        return UpdatesDifference(
            new_messages=[],
            new_encrypted_messages=[],
            other_updates=[trigger],
            chats=[min_channel],
            users=[],
            state=TlUpdatesState(pts=11, qts=0, date=150, seq=6, unread_count=0),
        )

    engine = UpdatesEngine(
        invoke_api=invoke,
        resolve_input_channel=lambda _channel_id: None,
    )
    state = asyncio.run(
        engine.initialize(initial_state=UpdatesState(pts=10, qts=0, date=100, seq=5))
    )
    catch_up = engine.take_initial_catch_up()

    assert len(calls) == 1
    assert state == UpdatesState(pts=11, qts=0, date=150, seq=6)
    assert catch_up is not None
    assert catch_up[1].updates == []
    assert catch_up[1].new_messages == []


def test_unexpected_channel_rpc_error_still_propagates_transactionally() -> None:
    async def invoke(_req: Any) -> Any:
        raise RpcErrorException(code=500, message="RPC_CALL_FAIL")

    engine = UpdatesEngine(
        invoke_api=invoke,
        resolve_input_channel=lambda channel_id: InputChannel(
            channel_id=channel_id,
            access_hash=789,
        ),
    )
    engine.state = UpdatesState(pts=10, qts=0, date=100, seq=5)
    engine._channel_pts[123] = 8

    with pytest.raises(RpcErrorException, match="RPC_CALL_FAIL"):
        asyncio.run(engine.apply(UpdateChannelTooLong(flags=0, channel_id=123, pts=None)))

    assert engine.state == UpdatesState(pts=10, qts=0, date=100, seq=5)
    assert engine._channel_pts[123] == 8
