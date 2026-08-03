from __future__ import annotations

import asyncio
from typing import Any

import pytest

from telecraft.mtproto.updates.engine import UpdatesEngine, UpdatesEngineError
from telecraft.mtproto.updates.state import UpdatesState
from telecraft.tl.generated.types import (
    ChannelMessagesFilterEmpty,
    InputChannel,
    UpdateChannel,
    UpdateChannelTooLong,
    UpdatesChannelDifferenceEmpty,
)


def test_update_channel_too_long_triggers_get_channel_difference() -> None:
    calls: list[Any] = []

    async def invoke(req: Any) -> Any:
        calls.append(req)
        # Return "empty" diff with same pts.
        return UpdatesChannelDifferenceEmpty(flags=0, final=True, pts=1, timeout=None)

    eng = UpdatesEngine(
        invoke_api=invoke,
        resolve_input_channel=lambda cid: InputChannel(channel_id=int(cid), access_hash=123),
    )
    eng.state = UpdatesState(pts=1, qts=1, date=0, seq=0)

    async def _run() -> None:
        await eng.apply(UpdateChannelTooLong(flags=0, channel_id=100, pts=None))

    asyncio.run(_run())

    assert calls, "expected getChannelDifference call"
    req0 = calls[0]
    assert getattr(req0, "TL_NAME", None) == "updates.getChannelDifference"
    assert isinstance(getattr(req0, "filter", None), ChannelMessagesFilterEmpty)


def test_update_channel_metadata_does_not_claim_a_channel_pts_gap() -> None:
    async def invoke(_req: Any) -> Any:
        raise AssertionError("updateChannel is not updateChannelTooLong")

    eng = UpdatesEngine(invoke_api=invoke)
    eng.state = UpdatesState(pts=1, qts=1, date=0, seq=0)
    update = UpdateChannel(channel_id=100)

    applied = asyncio.run(eng.apply(update))

    assert applied.updates == [update]


def test_channel_difference_rejects_no_progress_after_initial_force_transition() -> None:
    calls: list[Any] = []

    async def invoke(req: Any) -> Any:
        calls.append(req)
        return UpdatesChannelDifferenceEmpty(flags=0, final=False, pts=1, timeout=None)

    eng = UpdatesEngine(
        invoke_api=invoke,
        resolve_input_channel=lambda cid: InputChannel(channel_id=int(cid), access_hash=123),
    )
    eng.state = UpdatesState(pts=1, qts=1, date=0, seq=0)

    with pytest.raises(UpdatesEngineError, match="made no state progress"):
        asyncio.run(eng.apply(UpdateChannelTooLong(flags=0, channel_id=100, pts=None)))

    # The first same-PTS response is a valid force=True -> force=False state
    # transition.  A second identical non-final page cannot make progress.
    assert [call.force for call in calls] == [True, False]
    assert [call.pts for call in calls] == [1, 1]
    assert 100 not in eng._channel_pts
