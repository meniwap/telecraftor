from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from telecraft.mtproto.updates.engine import UpdatesEngine
from telecraft.mtproto.updates.state import UpdatesState
from telecraft.mtproto.updates.storage import (
    LegacyUpdatesStateMigrationRequired,
    UpdatesStateStorageError,
    load_updates_state_file,
    save_updates_state_file,
)
from telecraft.tl.generated.functions import UpdatesGetDifference
from telecraft.tl.generated.types import UpdatesDifferenceEmpty


def test_updates_state_storage_roundtrip(tmp_path) -> None:
    p = tmp_path / "x.updates.json"
    st = UpdatesState(
        pts=123,
        qts=456,
        date=789,
        seq=10,
        channel_pts={100: 80, 200: 9},
    )
    save_updates_state_file(p, st, auth_key_id="0123456789abcdef")
    got = load_updates_state_file(p, expected_auth_key_id="0123456789abcdef")
    assert got == st
    assert got.channel_pts == {100: 80, 200: 9}
    assert json.loads(p.read_text(encoding="utf-8")) == {
        "version": 3,
        "auth_key_id": "0123456789abcdef",
        "pts": 123,
        "qts": 456,
        "date": 789,
        "seq": 10,
        "channel_pts": {"100": 80, "200": 9},
    }


def test_updates_state_storage_rejects_different_or_unbound_authorization(tmp_path) -> None:
    p = tmp_path / "x.updates.json"
    st = UpdatesState(pts=123, qts=456, date=789, seq=10)
    save_updates_state_file(p, st, auth_key_id="0123456789abcdef")

    with pytest.raises(UpdatesStateStorageError, match="different authorization"):
        load_updates_state_file(p, expected_auth_key_id="fedcba9876543210")

    legacy = tmp_path / "legacy.updates.json"
    legacy.write_text(
        json.dumps({"version": 1, "pts": 1, "qts": 2, "date": 3, "seq": 4}),
        encoding="utf-8",
    )
    assert load_updates_state_file(legacy) == UpdatesState(pts=1, qts=2, date=3, seq=4)
    with pytest.raises(LegacyUpdatesStateMigrationRequired, match="not bound"):
        load_updates_state_file(legacy, expected_auth_key_id="0123456789abcdef")
    assert load_updates_state_file(
        legacy,
        expected_auth_key_id="0123456789abcdef",
        allow_unbound_legacy=True,
    ) == UpdatesState(pts=1, qts=2, date=3, seq=4)


def test_updates_state_storage_rejects_bad_version(tmp_path) -> None:
    p = tmp_path / "x.updates.json"
    p.write_text(
        json.dumps({"version": 999, "pts": 1, "qts": 2, "date": 3, "seq": 4}) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(UpdatesStateStorageError):
        _ = load_updates_state_file(p)


def test_v2_checkpoint_loads_with_empty_channel_cursors(tmp_path) -> None:
    p = tmp_path / "v2.updates.json"
    p.write_text(
        json.dumps(
            {
                "version": 2,
                "auth_key_id": "0123456789abcdef",
                "pts": 1,
                "qts": 2,
                "date": 3,
                "seq": 4,
            }
        ),
        encoding="utf-8",
    )

    state = load_updates_state_file(p, expected_auth_key_id="0123456789abcdef")

    assert state == UpdatesState(pts=1, qts=2, date=3, seq=4)
    assert state.channel_pts == {}


@pytest.mark.parametrize(
    "channel_pts",
    [
        {"0": 1},
        {"-1": 1},
        {"abc": 1},
        {"1": -1},
        {"1": True},
        {"1": "bad"},
        {"1": 1, "01": 2},
    ],
)
def test_v3_checkpoint_rejects_invalid_channel_cursors(tmp_path, channel_pts) -> None:
    p = tmp_path / "bad-channel.updates.json"
    p.write_text(
        json.dumps(
            {
                "version": 3,
                "auth_key_id": "0123456789abcdef",
                "pts": 1,
                "qts": 2,
                "date": 3,
                "seq": 4,
                "channel_pts": channel_pts,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(UpdatesStateStorageError):
        load_updates_state_file(p, expected_auth_key_id="0123456789abcdef")


def test_channel_cursor_survives_restart_without_a_new_channel_event(tmp_path) -> None:
    p = tmp_path / "restart.updates.json"
    auth_key_id = "0123456789abcdef"

    async def unused_invoke(_req: Any) -> Any:
        raise AssertionError("the first process only creates a durable checkpoint")

    first_process = UpdatesEngine(invoke_api=unused_invoke)
    first_process.state = UpdatesState(pts=10, qts=2, date=100, seq=3)
    first_process._channel_pts[100] = 80
    save_updates_state_file(
        p,
        first_process.checkpoint(),
        auth_key_id=auth_key_id,
    )

    loaded = load_updates_state_file(p, expected_auth_key_id=auth_key_id)
    calls: list[Any] = []

    async def invoke(req: Any) -> Any:
        calls.append(req)
        assert isinstance(req, UpdatesGetDifference)
        return UpdatesDifferenceEmpty(date=101, seq=4)

    restarted_process = UpdatesEngine(invoke_api=invoke)
    asyncio.run(restarted_process.initialize(initial_state=loaded))

    assert len(calls) == 1
    assert restarted_process._channel_pts == {100: 80}
    # No channel event has arrived. A subsequent shutdown checkpoint must still
    # retain the cursor learned by the previous process.
    save_updates_state_file(
        p,
        restarted_process.checkpoint(),
        auth_key_id=auth_key_id,
    )
    reloaded = load_updates_state_file(p, expected_auth_key_id=auth_key_id)
    assert reloaded.channel_pts == {100: 80}
