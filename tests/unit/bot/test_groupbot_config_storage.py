from __future__ import annotations

import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from telecraft.bot.groupbot import (
    GroupBotConfig,
    GroupBotConfigurationError,
    GroupBotStorage,
    load_group_bot_config,
    validate_group_bot_config,
    validate_group_bot_scope,
)


def test_groupbot_config__load_defaults__returns_expected_shape() -> None:
    with TemporaryDirectory() as td:
        cfg = load_group_bot_config(Path(td) / "missing.json")
        assert cfg.read_only_mode is True
        assert cfg.allow_all_peers is False
        assert cfg.max_concurrent_handlers == 64
        assert cfg.max_pending_handlers == 4096
        assert cfg.enable_moderation is True
        assert cfg.warn_threshold >= 1


def test_groupbot_config__parse_values__returns_expected_shape() -> None:
    with TemporaryDirectory() as td:
        path = Path(td) / "bot_config.json"
        path.write_text(
            json.dumps(
                {
                    "allowed_peers": ["@demo", "channel:123"],
                    "allow_all_peers": False,
                    "admin_user_ids": [1, "2"],
                    "read_only_mode": False,
                    "warn_threshold": 5,
                    "max_concurrent_handlers": 12,
                    "max_pending_handlers": 300,
                    "announcements": [
                        {
                            "name": "a",
                            "text": "b",
                            "every_seconds": 60,
                            "peer": "channel:1",
                            "enabled": True,
                        }
                    ],
                }
            ),
            encoding="utf-8",
            newline="\n",
        )
        cfg = load_group_bot_config(path)
        assert cfg.read_only_mode is False
        assert cfg.allow_all_peers is False
        assert cfg.warn_threshold == 5
        assert cfg.max_concurrent_handlers == 12
        assert cfg.max_pending_handlers == 300
        assert cfg.admin_user_ids == [1, 2]
        assert len(cfg.announcements) == 1


def test_groupbot_config__invalid_boolean_uses_safe_default(tmp_path: Path) -> None:
    path = tmp_path / "invalid-bool.json"
    path.write_text(
        json.dumps(
            {
                "allowed_peers": ["channel:1"],
                "read_only_mode": "invalid",
                "allow_all_peers": "invalid",
            }
        ),
        encoding="utf-8",
    )
    cfg = load_group_bot_config(path)
    assert cfg.read_only_mode is True
    assert cfg.allow_all_peers is False


@pytest.mark.parametrize(
    "config",
    [
        GroupBotConfig(allowed_peers=["channel:1"]),
        GroupBotConfig(allowed_peers=["@demo_user"]),
        GroupBotConfig(allow_all_peers=True),
    ],
)
def test_groupbot_config__valid_scope_is_accepted(config: GroupBotConfig) -> None:
    validate_group_bot_scope(config)


@pytest.mark.parametrize(
    ("config", "message"),
    [
        (GroupBotConfig(), "allowed_peers"),
        (
            GroupBotConfig(allowed_peers=["channel:1"], allow_all_peers=True),
            "cannot be combined",
        ),
        (GroupBotConfig(allowed_peers=["not-a-peer"]), "invalid entries"),
        (GroupBotConfig(allowed_peers=["@abc"]), "invalid entries"),
    ],
)
def test_groupbot_config__invalid_scope_is_rejected(
    config: GroupBotConfig,
    message: str,
) -> None:
    with pytest.raises(GroupBotConfigurationError, match=message):
        validate_group_bot_scope(config)


def test_groupbot_config__pending_limit_cannot_be_smaller_than_concurrency() -> None:
    config = GroupBotConfig(
        allowed_peers=["channel:1"],
        max_concurrent_handlers=10,
        max_pending_handlers=9,
    )
    with pytest.raises(GroupBotConfigurationError, match="max_pending_handlers"):
        validate_group_bot_config(config)


def test_groupbot_storage__warnings_stats_logs__returns_expected_shape() -> None:
    with TemporaryDirectory() as td:
        db = GroupBotStorage(Path(td) / "groupbot.sqlite3")
        try:
            key = "channel:123"
            assert db.get_warning_count(peer_key=key, user_id=10) == 0
            count = db.increment_warning(peer_key=key, user_id=10, reason="manual")
            assert count == 1
            count2 = db.increment_warning(peer_key=key, user_id=10, reason="manual")
            assert count2 == 2
            db.reset_warning(peer_key=key, user_id=10)
            assert db.get_warning_count(peer_key=key, user_id=10) == 0

            mc1 = db.increment_message_count(peer_key=key, user_id=10)
            mc2 = db.increment_message_count(peer_key=key, user_id=10)
            assert mc1 == 1
            assert mc2 == 2
            top = db.list_top_users(peer_key=key, limit=5)
            assert top[0] == (10, 2)

            _ = db.add_mod_log(
                peer_key=key,
                action="warn",
                actor_id=1,
                target_user_id=10,
                details={"reason": "manual"},
            )
            rows = db.list_mod_log(peer_key=key, limit=5)
            assert rows
            assert rows[0]["action"] == "warn"

            db.upsert_scheduled_job(
                name="job-a",
                text="hi",
                interval_seconds=60,
                peer_ref=key,
                enabled=True,
            )
            jobs = db.list_scheduled_jobs(enabled_only=True)
            assert len(jobs) == 1
            assert jobs[0].name == "job-a"
            assert jobs[0].source == "manual"
            assert jobs[0].suppressed is False
            assert db.set_scheduled_job_state(
                name="job-a",
                enabled=False,
                suppressed=True,
            )
            disabled = db.get_scheduled_job(name="job-a")
            assert disabled is not None
            assert disabled.enabled is False
            assert disabled.suppressed is True
            assert db.delete_scheduled_job(name="job-a") is True
            assert db.delete_scheduled_job(name="job-a") is False
            assert db.list_scheduled_jobs(enabled_only=False) == []
        finally:
            db.close()


def test_groupbot_storage__migrates_legacy_schedule_schema(tmp_path: Path) -> None:
    path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE scheduled_jobs (
                name TEXT PRIMARY KEY,
                peer_ref TEXT,
                text TEXT NOT NULL,
                interval_seconds INTEGER NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                last_run_ts INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            INSERT INTO scheduled_jobs(
                name, peer_ref, text, interval_seconds, enabled, last_run_ts
            ) VALUES ('legacy', 'channel:1', 'hello', 60, 1, 0)
            """
        )

    db = GroupBotStorage(path)
    try:
        job = db.get_scheduled_job(name="legacy")
        assert job is not None
        assert job.source == "manual"
        assert job.suppressed is False
    finally:
        db.close()


def test_groupbot_storage__serializes_concurrent_legacy_migration(tmp_path: Path) -> None:
    path = tmp_path / "legacy-concurrent.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE scheduled_jobs (
                name TEXT PRIMARY KEY,
                peer_ref TEXT,
                text TEXT NOT NULL,
                interval_seconds INTEGER NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                last_run_ts INTEGER NOT NULL DEFAULT 0
            )
            """
        )

    start = threading.Barrier(8)

    def _open_and_close() -> None:
        start.wait()
        db = GroupBotStorage(path)
        db.close()

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _index: _open_and_close(), range(8)))

    db = GroupBotStorage(path)
    try:
        with sqlite3.connect(path) as conn:
            columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(scheduled_jobs)")}
        assert {"source", "suppressed"} <= columns
    finally:
        db.close()


def test_groupbot_storage__retries_complete_initialization_after_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = GroupBotStorage._init_schema_once
    attempts = 0

    def _locked_then_initialize(self: GroupBotStorage) -> None:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise sqlite3.OperationalError("database is locked")
        original(self)

    monkeypatch.setattr(GroupBotStorage, "_init_schema_once", _locked_then_initialize)

    db = GroupBotStorage(tmp_path / "retry.sqlite3")
    try:
        assert attempts == 3
        db.set_group_setting(peer_key="channel:1", key="ready", value=True)
        assert db.get_group_setting(peer_key="channel:1", key="ready") is True
    finally:
        db.close()


def test_groupbot_storage__does_not_retry_unrelated_operational_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0

    def _fail_initialization(_self: GroupBotStorage) -> None:
        nonlocal attempts
        attempts += 1
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(GroupBotStorage, "_init_schema_once", _fail_initialization)

    with pytest.raises(sqlite3.OperationalError, match="disk I/O error"):
        GroupBotStorage(tmp_path / "broken.sqlite3")

    assert attempts == 1
