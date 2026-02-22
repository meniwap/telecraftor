from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast

BacklogPolicy = Literal["ignore", "process_no_reply", "process_all"]
ThrottleMode = Literal["sleep", "drop"]


@dataclass(slots=True, frozen=True)
class ScheduledAnnouncement:
    name: str
    text: str
    every_seconds: int
    peer: str | None = None
    enabled: bool = True


@dataclass(slots=True)
class GroupBotConfig:
    allowed_peers: list[str] = field(default_factory=list)
    admin_user_ids: list[int] = field(default_factory=list)
    audit_peer: str | None = None
    storage_path: str = ".sessions/group_bot.sqlite3"
    plugin_paths: list[str] = field(default_factory=list)

    read_only_mode: bool = True
    enable_moderation: bool = True
    enable_stats: bool = True
    enable_welcome: bool = True
    enable_utilities: bool = True
    enable_inline: bool = False

    warn_threshold: int = 3
    flood_message_count: int = 8
    flood_window_seconds: int = 10
    flood_cooldown_seconds: int = 45
    auto_mute_minutes: int = 2
    block_links: bool = True
    blocked_keywords: list[str] = field(default_factory=list)

    backlog_policy: BacklogPolicy = "process_no_reply"
    backlog_grace_seconds: int = 60
    throttle_global_per_minute: int | None = 240
    throttle_peer_per_minute: int | None = 60
    throttle_burst: int = 10
    throttle_mode: ThrottleMode = "sleep"
    debug_dispatcher: bool = False

    announcements: list[ScheduledAnnouncement] = field(default_factory=list)


def _as_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return default


def _as_int(value: Any, *, default: int, min_value: int | None = None) -> int:
    if value is None:
        out = default
    elif isinstance(value, bool):
        out = int(value)
    elif isinstance(value, (int, float)):
        out = int(value)
    elif isinstance(value, str):
        try:
            out = int(value.strip())
        except ValueError:
            out = default
    else:
        out = default
    if min_value is not None and out < min_value:
        return min_value
    return out


def _as_optional_int(value: Any, *, default: int | None) -> int | None:
    if value is None:
        return default
    if isinstance(value, str) and value.strip().lower() in {"none", "null", ""}:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return default
    return default


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        normalized = item.strip()
        if normalized:
            out.append(normalized)
    return out


def _as_int_list(value: Any) -> list[int]:
    if not isinstance(value, list):
        return []
    out: list[int] = []
    for item in value:
        if isinstance(item, bool):
            out.append(int(item))
            continue
        if isinstance(item, (int, float)):
            out.append(int(item))
            continue
        if isinstance(item, str):
            try:
                out.append(int(item.strip()))
            except ValueError:
                continue
    return out


def _parse_announcements(value: Any) -> list[ScheduledAnnouncement]:
    if not isinstance(value, list):
        return []
    out: list[ScheduledAnnouncement] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        name_raw = item.get("name")
        text_raw = item.get("text")
        every_raw = item.get("every_seconds")
        if not isinstance(name_raw, str) or not isinstance(text_raw, str):
            continue
        name = name_raw.strip()
        text = text_raw.strip()
        if not name or not text:
            continue
        every_seconds = _as_int(every_raw, default=0, min_value=0)
        if every_seconds <= 0:
            continue
        peer_raw = item.get("peer")
        peer = peer_raw.strip() if isinstance(peer_raw, str) and peer_raw.strip() else None
        enabled = _as_bool(item.get("enabled"), default=True)
        out.append(
            ScheduledAnnouncement(
                name=name,
                text=text,
                every_seconds=every_seconds,
                peer=peer,
                enabled=enabled,
            )
        )
    return out


def load_group_bot_config(path: str | Path) -> GroupBotConfig:
    """
    Load group-bot JSON config with safe defaults.

    If file does not exist, defaults are returned.
    """
    p = Path(path).expanduser()
    if not p.exists():
        return GroupBotConfig()

    raw = p.read_text(encoding="utf-8")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid group-bot config at {p}: root must be an object")
    data = cast(dict[str, Any], payload)

    backlog_policy_raw = data.get("backlog_policy")
    backlog_policy: BacklogPolicy = "process_no_reply"
    if backlog_policy_raw in {"ignore", "process_no_reply", "process_all"}:
        backlog_policy = cast(BacklogPolicy, backlog_policy_raw)

    throttle_mode_raw = data.get("throttle_mode")
    throttle_mode: ThrottleMode = "sleep"
    if throttle_mode_raw in {"sleep", "drop"}:
        throttle_mode = cast(ThrottleMode, throttle_mode_raw)

    blocked_keywords = [kw.lower() for kw in _as_str_list(data.get("blocked_keywords"))]
    audit_peer_raw = data.get("audit_peer")
    storage_path_raw = data.get("storage_path")
    audit_peer = audit_peer_raw.strip() if isinstance(audit_peer_raw, str) else ""
    storage_path = storage_path_raw.strip() if isinstance(storage_path_raw, str) else ""

    return GroupBotConfig(
        allowed_peers=_as_str_list(data.get("allowed_peers")),
        admin_user_ids=_as_int_list(data.get("admin_user_ids")),
        audit_peer=audit_peer if audit_peer else None,
        storage_path=storage_path if storage_path else ".sessions/group_bot.sqlite3",
        plugin_paths=_as_str_list(data.get("plugin_paths")),
        read_only_mode=_as_bool(data.get("read_only_mode"), default=True),
        enable_moderation=_as_bool(data.get("enable_moderation"), default=True),
        enable_stats=_as_bool(data.get("enable_stats"), default=True),
        enable_welcome=_as_bool(data.get("enable_welcome"), default=True),
        enable_utilities=_as_bool(data.get("enable_utilities"), default=True),
        enable_inline=_as_bool(data.get("enable_inline"), default=False),
        warn_threshold=_as_int(data.get("warn_threshold"), default=3, min_value=1),
        flood_message_count=_as_int(data.get("flood_message_count"), default=8, min_value=2),
        flood_window_seconds=_as_int(data.get("flood_window_seconds"), default=10, min_value=1),
        flood_cooldown_seconds=_as_int(
            data.get("flood_cooldown_seconds"),
            default=45,
            min_value=1,
        ),
        auto_mute_minutes=_as_int(data.get("auto_mute_minutes"), default=2, min_value=0),
        block_links=_as_bool(data.get("block_links"), default=True),
        blocked_keywords=blocked_keywords,
        backlog_policy=backlog_policy,
        backlog_grace_seconds=_as_int(data.get("backlog_grace_seconds"), default=60, min_value=0),
        throttle_global_per_minute=_as_optional_int(
            data.get("throttle_global_per_minute"),
            default=240,
        ),
        throttle_peer_per_minute=_as_optional_int(
            data.get("throttle_peer_per_minute"),
            default=60,
        ),
        throttle_burst=_as_int(data.get("throttle_burst"), default=10, min_value=1),
        throttle_mode=throttle_mode,
        debug_dispatcher=_as_bool(data.get("debug_dispatcher"), default=False),
        announcements=_parse_announcements(data.get("announcements")),
    )
