from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from telecraft.bot.groupbot import GroupBotStorage, load_group_bot_config


def test_groupbot_config__load_defaults__returns_expected_shape() -> None:
    with TemporaryDirectory() as td:
        cfg = load_group_bot_config(Path(td) / "missing.json")
        assert cfg.read_only_mode is True
        assert cfg.enable_moderation is True
        assert cfg.warn_threshold >= 1


def test_groupbot_config__parse_values__returns_expected_shape() -> None:
    with TemporaryDirectory() as td:
        path = Path(td) / "bot_config.json"
        path.write_text(
            json.dumps(
                {
                    "allowed_peers": ["@demo", "channel:123"],
                    "admin_user_ids": [1, "2"],
                    "read_only_mode": False,
                    "warn_threshold": 5,
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
        assert cfg.warn_threshold == 5
        assert cfg.admin_user_ids == [1, 2]
        assert len(cfg.announcements) == 1


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
        finally:
            db.close()
