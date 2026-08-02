from __future__ import annotations

import json

import pytest

from telecraft.mtproto.updates.state import UpdatesState
from telecraft.mtproto.updates.storage import (
    LegacyUpdatesStateMigrationRequired,
    UpdatesStateStorageError,
    load_updates_state_file,
    save_updates_state_file,
)


def test_updates_state_storage_roundtrip(tmp_path) -> None:
    p = tmp_path / "x.updates.json"
    st = UpdatesState(pts=123, qts=456, date=789, seq=10)
    save_updates_state_file(p, st, auth_key_id="0123456789abcdef")
    got = load_updates_state_file(p, expected_auth_key_id="0123456789abcdef")
    assert got == st


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
