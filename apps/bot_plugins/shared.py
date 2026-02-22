from __future__ import annotations

import re
import time
from typing import Any

from telecraft.bot.events import MessageEvent
from telecraft.bot.groupbot import GroupBotContext, get_group_bot_context
from telecraft.bot.router import Router

_LINK_RE = re.compile(r"(https?://|t\.me/|www\.)", flags=re.IGNORECASE)
RESTRICT_PROFILES: tuple[str, ...] = ("all", "media", "links", "text")
_RESTRICT_PROFILE_ALIASES: dict[str, str] = {
    "all": "all",
    "full": "all",
    "mute": "all",
    "media": "media",
    "photo": "media",
    "photos": "media",
    "video": "media",
    "videos": "media",
    "docs": "media",
    "files": "media",
    "link": "links",
    "links": "links",
    "url": "links",
    "urls": "links",
    "text": "text",
    "plain": "text",
}


def ctx_from_router(router: Router) -> GroupBotContext:
    return get_group_bot_context(router)


def peer_ref(peer_type: str | None, peer_id: int | None) -> str | None:
    if peer_type is None or peer_id is None:
        return None
    return f"{peer_type}:{int(peer_id)}"


async def require_admin(
    *,
    ctx: GroupBotContext,
    event: MessageEvent,
    action_name: str,
) -> bool:
    is_admin = await ctx.is_admin(
        peer_type=event.peer_type,
        peer_id=event.peer_id,
        user_id=event.sender_id,
    )
    if is_admin:
        return True
    await event.reply(f"אין הרשאה לפקודה `{action_name}`.")
    return False


async def dry_run_guard(
    *,
    ctx: GroupBotContext,
    event: MessageEvent,
    action: str,
    details: str,
) -> bool:
    key = ctx.event_peer_key(event)
    if not ctx.get_peer_read_only(key):
        return False
    await event.reply(f"[dry-run] {action}: {details}")
    await ctx.send_audit(f"[DRY-RUN] {action} peer={key} details={details}")
    return True


async def resolve_user_ref(ctx: GroupBotContext, raw_target: str) -> tuple[int, str]:
    target = raw_target.strip()
    if not target:
        raise ValueError("missing target")
    peer = await ctx.app.raw.resolve_peer(target, timeout=ctx.timeout)
    if peer.peer_type != "user":
        raise ValueError("target must resolve to a user")
    user_id = int(peer.peer_id)
    return user_id, f"user:{user_id}"


def parse_target_and_rest(args: str) -> tuple[str, str]:
    head, _, rest = args.strip().partition(" ")
    return head.strip(), rest.strip()


def parse_minutes_target(args: str) -> tuple[int, str]:
    tokens = [token for token in args.strip().split(" ") if token]
    if len(tokens) < 2:
        raise ValueError("usage: /mute <target> <minutes>")
    first, second = tokens[0], tokens[1]

    if first.lstrip("+-").isdigit():
        return int(first), second
    if second.lstrip("+-").isdigit():
        return int(second), first
    raise ValueError("usage: /mute <target> <minutes>")


def normalize_restrict_profile(raw_profile: str) -> str:
    token = raw_profile.strip().lower()
    if not token:
        raise ValueError("missing restriction profile")
    profile = _RESTRICT_PROFILE_ALIASES.get(token)
    if profile is None:
        allowed = ", ".join(RESTRICT_PROFILES)
        raise ValueError(f"unknown restriction profile {raw_profile!r}; use one of: {allowed}")
    return profile


def parse_restrict_args(
    args: str,
    *,
    default_minutes: int,
) -> tuple[str, str, int]:
    """
    Parse restriction command arguments with a few operator-friendly shapes:
    - /restrict <target> <profile> [minutes]
    - /restrict <target> <minutes> [profile]
    """
    tokens = [token for token in args.strip().split(" ") if token]
    if len(tokens) < 2:
        raise ValueError("usage: /restrict <target> <profile> [minutes]")
    if len(tokens) > 3:
        raise ValueError("usage: /restrict <target> <profile> [minutes]")

    target = tokens[0]
    minutes = int(default_minutes)
    profile = "all"

    second = tokens[1]
    if second.lstrip("+-").isdigit():
        minutes = int(second)
        if len(tokens) >= 3:
            profile = normalize_restrict_profile(tokens[2])
    else:
        profile = normalize_restrict_profile(second)
        if len(tokens) >= 3:
            third = tokens[2]
            if not third.lstrip("+-").isdigit():
                raise ValueError("minutes must be a number")
            minutes = int(third)

    if minutes <= 0:
        raise ValueError("minutes must be > 0")
    return target, profile, minutes


def has_link(text: str) -> bool:
    return _LINK_RE.search(text) is not None


def has_blocked_keyword(text: str, keywords: list[str]) -> str | None:
    lowered = text.lower()
    for keyword in keywords:
        token = keyword.strip().lower()
        if token and token in lowered:
            return token
    return None


def now_ts() -> int:
    return int(time.time())


def decode_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)
