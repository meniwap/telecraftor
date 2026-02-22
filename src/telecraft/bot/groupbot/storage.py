from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True, frozen=True)
class ScheduledJobRecord:
    name: str
    peer_ref: str | None
    text: str
    interval_seconds: int
    enabled: bool
    last_run_ts: int


class GroupBotStorage:
    def __init__(self, path: str | Path) -> None:
        p = Path(path).expanduser()
        if not p.is_absolute():
            p = (Path.cwd() / p).resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        self.path = p
        self._conn = sqlite3.connect(str(p), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._init_schema()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                PRAGMA journal_mode=WAL;

                CREATE TABLE IF NOT EXISTS group_settings (
                    peer_key TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value_json TEXT NOT NULL,
                    PRIMARY KEY (peer_key, key)
                );

                CREATE TABLE IF NOT EXISTS user_stats (
                    peer_key TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    message_count INTEGER NOT NULL DEFAULT 0,
                    last_seen_ts INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (peer_key, user_id)
                );

                CREATE TABLE IF NOT EXISTS warnings (
                    peer_key TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    count INTEGER NOT NULL DEFAULT 0,
                    updated_ts INTEGER NOT NULL DEFAULT 0,
                    last_reason TEXT,
                    PRIMARY KEY (peer_key, user_id)
                );

                CREATE TABLE IF NOT EXISTS mod_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts INTEGER NOT NULL,
                    peer_key TEXT NOT NULL,
                    action TEXT NOT NULL,
                    actor_id INTEGER,
                    target_user_id INTEGER,
                    details_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_mod_log_peer_ts
                    ON mod_log (peer_key, ts DESC);

                CREATE TABLE IF NOT EXISTS scheduled_jobs (
                    name TEXT PRIMARY KEY,
                    peer_ref TEXT,
                    text TEXT NOT NULL,
                    interval_seconds INTEGER NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    last_run_ts INTEGER NOT NULL DEFAULT 0
                );
                """
            )
            self._conn.commit()

    def set_group_setting(self, *, peer_key: str, key: str, value: Any) -> None:
        payload = json.dumps(value, ensure_ascii=False)
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO group_settings(peer_key, key, value_json)
                VALUES (?, ?, ?)
                ON CONFLICT(peer_key, key) DO UPDATE SET value_json=excluded.value_json
                """,
                (peer_key, key, payload),
            )
            self._conn.commit()

    def get_group_setting(self, *, peer_key: str, key: str, default: Any = None) -> Any:
        with self._lock:
            row = self._conn.execute(
                "SELECT value_json FROM group_settings WHERE peer_key=? AND key=?",
                (peer_key, key),
            ).fetchone()
        if row is None:
            return default
        raw = row["value_json"]
        if not isinstance(raw, str):
            return default
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return default

    def increment_message_count(self, *, peer_key: str, user_id: int, ts: int | None = None) -> int:
        now = int(time.time()) if ts is None else int(ts)
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO user_stats(peer_key, user_id, message_count, last_seen_ts)
                VALUES (?, ?, 1, ?)
                ON CONFLICT(peer_key, user_id) DO UPDATE SET
                    message_count = user_stats.message_count + 1,
                    last_seen_ts = excluded.last_seen_ts
                """,
                (peer_key, int(user_id), now),
            )
            row = self._conn.execute(
                "SELECT message_count FROM user_stats WHERE peer_key=? AND user_id=?",
                (peer_key, int(user_id)),
            ).fetchone()
            self._conn.commit()
        if row is None:
            return 0
        return int(row["message_count"])

    def get_user_stats(self, *, peer_key: str, user_id: int) -> dict[str, int]:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT message_count, last_seen_ts
                FROM user_stats
                WHERE peer_key=? AND user_id=?
                """,
                (peer_key, int(user_id)),
            ).fetchone()
        if row is None:
            return {"message_count": 0, "last_seen_ts": 0}
        return {
            "message_count": int(row["message_count"]),
            "last_seen_ts": int(row["last_seen_ts"]),
        }

    def list_top_users(self, *, peer_key: str, limit: int = 10) -> list[tuple[int, int]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT user_id, message_count
                FROM user_stats
                WHERE peer_key=?
                ORDER BY message_count DESC, user_id ASC
                LIMIT ?
                """,
                (peer_key, int(limit)),
            ).fetchall()
        out: list[tuple[int, int]] = []
        for row in rows:
            out.append((int(row["user_id"]), int(row["message_count"])))
        return out

    def increment_warning(
        self,
        *,
        peer_key: str,
        user_id: int,
        reason: str | None = None,
        ts: int | None = None,
    ) -> int:
        now = int(time.time()) if ts is None else int(ts)
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO warnings(peer_key, user_id, count, updated_ts, last_reason)
                VALUES (?, ?, 1, ?, ?)
                ON CONFLICT(peer_key, user_id) DO UPDATE SET
                    count = warnings.count + 1,
                    updated_ts = excluded.updated_ts,
                    last_reason = excluded.last_reason
                """,
                (peer_key, int(user_id), now, reason),
            )
            row = self._conn.execute(
                "SELECT count FROM warnings WHERE peer_key=? AND user_id=?",
                (peer_key, int(user_id)),
            ).fetchone()
            self._conn.commit()
        if row is None:
            return 0
        return int(row["count"])

    def reset_warning(self, *, peer_key: str, user_id: int, ts: int | None = None) -> None:
        now = int(time.time()) if ts is None else int(ts)
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO warnings(peer_key, user_id, count, updated_ts, last_reason)
                VALUES (?, ?, 0, ?, NULL)
                ON CONFLICT(peer_key, user_id) DO UPDATE SET
                    count = 0,
                    updated_ts = excluded.updated_ts,
                    last_reason = NULL
                """,
                (peer_key, int(user_id), now),
            )
            self._conn.commit()

    def get_warning_count(self, *, peer_key: str, user_id: int) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT count FROM warnings WHERE peer_key=? AND user_id=?",
                (peer_key, int(user_id)),
            ).fetchone()
        if row is None:
            return 0
        return int(row["count"])

    def add_mod_log(
        self,
        *,
        peer_key: str,
        action: str,
        actor_id: int | None,
        target_user_id: int | None,
        details: dict[str, Any] | None = None,
        ts: int | None = None,
    ) -> int:
        now = int(time.time()) if ts is None else int(ts)
        payload = json.dumps(details or {}, ensure_ascii=False, separators=(",", ":"))
        with self._lock:
            cur = self._conn.execute(
                """
                INSERT INTO mod_log(ts, peer_key, action, actor_id, target_user_id, details_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (now, peer_key, action, actor_id, target_user_id, payload),
            )
            self._conn.commit()
            last_id = cur.lastrowid
            return int(last_id) if isinstance(last_id, int) else 0

    def list_mod_log(self, *, peer_key: str, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT ts, action, actor_id, target_user_id, details_json
                FROM mod_log
                WHERE peer_key=?
                ORDER BY ts DESC, id DESC
                LIMIT ?
                """,
                (peer_key, int(limit)),
            ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            details_raw = row["details_json"]
            details: dict[str, Any] = {}
            if isinstance(details_raw, str):
                try:
                    parsed = json.loads(details_raw)
                    if isinstance(parsed, dict):
                        details = parsed
                except json.JSONDecodeError:
                    details = {}
            out.append(
                {
                    "ts": int(row["ts"]),
                    "action": str(row["action"]),
                    "actor_id": int(row["actor_id"]) if row["actor_id"] is not None else None,
                    "target_user_id": (
                        int(row["target_user_id"]) if row["target_user_id"] is not None else None
                    ),
                    "details": details,
                }
            )
        return out

    def upsert_scheduled_job(
        self,
        *,
        name: str,
        text: str,
        interval_seconds: int,
        peer_ref: str | None = None,
        enabled: bool = True,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO scheduled_jobs(
                    name,
                    peer_ref,
                    text,
                    interval_seconds,
                    enabled,
                    last_run_ts
                )
                VALUES (?, ?, ?, ?, ?, COALESCE(
                    (SELECT last_run_ts FROM scheduled_jobs WHERE name=?),
                    0
                ))
                ON CONFLICT(name) DO UPDATE SET
                    peer_ref = excluded.peer_ref,
                    text = excluded.text,
                    interval_seconds = excluded.interval_seconds,
                    enabled = excluded.enabled
                """,
                (
                    name,
                    peer_ref,
                    text,
                    int(interval_seconds),
                    1 if enabled else 0,
                    name,
                ),
            )
            self._conn.commit()

    def touch_scheduled_job(self, *, name: str, ts: int | None = None) -> None:
        now = int(time.time()) if ts is None else int(ts)
        with self._lock:
            self._conn.execute(
                "UPDATE scheduled_jobs SET last_run_ts=? WHERE name=?",
                (now, name),
            )
            self._conn.commit()

    def list_scheduled_jobs(self, *, enabled_only: bool = True) -> list[ScheduledJobRecord]:
        where = "WHERE enabled=1" if enabled_only else ""
        with self._lock:
            rows = self._conn.execute(
                f"""
                SELECT name, peer_ref, text, interval_seconds, enabled, last_run_ts
                FROM scheduled_jobs
                {where}
                ORDER BY name ASC
                """
            ).fetchall()
        out: list[ScheduledJobRecord] = []
        for row in rows:
            peer_raw = row["peer_ref"]
            peer_ref = str(peer_raw) if isinstance(peer_raw, str) and peer_raw else None
            out.append(
                ScheduledJobRecord(
                    name=str(row["name"]),
                    peer_ref=peer_ref,
                    text=str(row["text"]),
                    interval_seconds=int(row["interval_seconds"]),
                    enabled=bool(int(row["enabled"])),
                    last_run_ts=int(row["last_run_ts"]),
                )
            )
        return out
