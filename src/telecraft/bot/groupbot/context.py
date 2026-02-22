from __future__ import annotations

import logging
import re
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from telecraft.bot.router import Router
from telecraft.bot.scheduler import Scheduler
from telecraft.client import Client
from telecraft.client.peers import Peer

from .config import GroupBotConfig
from .storage import GroupBotStorage, ScheduledJobRecord

logger = logging.getLogger(__name__)
_CONTEXT_ATTR = "_group_bot_context"
_PEER_KEY_RE = re.compile(r"^(user|chat|channel):(-?\d+)$")


@dataclass(slots=True)
class GroupBotContext:
    app: Client
    router: Router
    scheduler: Scheduler
    storage: GroupBotStorage
    config: GroupBotConfig
    timeout: float = 20.0

    allowed_peer_keys: set[str] = field(default_factory=set)
    scheduled_names: set[str] = field(default_factory=set)
    admin_cache_ttl_seconds: int = 60

    _admin_cache: dict[tuple[str, int], tuple[bool, float]] = field(default_factory=dict)
    _flood_events: dict[tuple[str, int], deque[float]] = field(default_factory=dict)
    _flood_last_action: dict[tuple[str, int], float] = field(default_factory=dict)

    def peer_key(self, peer_type: str | None, peer_id: int | None) -> str | None:
        if peer_type is None or peer_id is None:
            return None
        return f"{peer_type}:{int(peer_id)}"

    def event_peer_key(self, event: Any) -> str | None:
        return self.peer_key(
            cast_maybe_str(getattr(event, "peer_type", None)),
            cast_maybe_int(getattr(event, "peer_id", None)),
        )

    def is_peer_allowed(self, peer_type: str | None, peer_id: int | None) -> bool:
        if not self.allowed_peer_keys:
            return True
        key = self.peer_key(peer_type, peer_id)
        if key is None:
            return False
        return key in self.allowed_peer_keys

    async def resolve_allowed_peer_keys(self) -> set[str]:
        refs = list(self.config.allowed_peers)
        if not refs:
            self.allowed_peer_keys = set()
            return set()
        out: set[str] = set()
        for ref in refs:
            parsed = parse_peer_key(ref)
            if parsed is not None:
                out.add(parsed)
                continue
            try:
                peer = await self.app.raw.resolve_peer(ref, timeout=self.timeout)
            except Exception as ex:  # noqa: BLE001
                logger.warning("Failed to resolve allowed peer %r: %s", ref, ex)
                continue
            key = self.peer_key(peer.peer_type, peer.peer_id)
            if key is not None:
                out.add(key)
        self.allowed_peer_keys = out
        return set(out)

    def get_peer_read_only(self, peer_key: str | None) -> bool:
        if peer_key is None:
            return bool(self.config.read_only_mode)
        value = self.storage.get_group_setting(
            peer_key=peer_key,
            key="read_only_mode",
            default=self.config.read_only_mode,
        )
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "y", "on"}
        if isinstance(value, (int, float)):
            return bool(value)
        return bool(self.config.read_only_mode)

    def set_peer_read_only(self, peer_key: str, enabled: bool) -> None:
        self.storage.set_group_setting(peer_key=peer_key, key="read_only_mode", value=bool(enabled))

    async def is_admin(
        self,
        *,
        peer_type: str | None,
        peer_id: int | None,
        user_id: int | None,
    ) -> bool:
        if user_id is None:
            return False
        uid = int(user_id)
        if uid in self.config.admin_user_ids:
            return True
        key = self.peer_key(peer_type, peer_id)
        if key is None:
            return False

        now = time.monotonic()
        cached = self._admin_cache.get((key, uid))
        if cached is not None and (now - cached[1]) <= float(self.admin_cache_ttl_seconds):
            return bool(cached[0])

        is_admin = False
        should_cache = True
        if peer_type == "channel" and peer_id is not None:
            channel_ref = f"channel:{int(peer_id)}"
            user_ref = f"user:{uid}"

            async def _lookup_once() -> bool:
                member = await self.app.admin.member(
                    channel_ref,
                    user_ref,
                    timeout=self.timeout,
                )
                name = str(getattr(member, "TL_NAME", "")).lower()
                return any(token in name for token in ("admin", "creator"))

            try:
                is_admin = await _lookup_once()
            except Exception as ex:  # noqa: BLE001
                should_cache = False
                err_text = str(getattr(ex, "message", ex))
                if "PEER_ID_INVALID" in err_text.upper():
                    try:
                        await self._refresh_admin_lookup_entities(
                            peer_id=int(peer_id),
                            user_id=uid,
                        )
                        is_admin = await _lookup_once()
                        should_cache = True
                    except Exception as retry_ex:  # noqa: BLE001
                        logger.info(
                            "is_admin retry failed peer=%s user=%s: %s",
                            key,
                            uid,
                            retry_ex,
                        )
                else:
                    logger.info("is_admin lookup failed peer=%s user=%s: %s", key, uid, ex)

        if should_cache:
            self._admin_cache[(key, uid)] = (is_admin, now)
        return is_admin

    async def _refresh_admin_lookup_entities(self, *, peer_id: int, user_id: int) -> None:
        raw = getattr(self.app, "raw", None)
        if raw is None:
            return
        prime_for_reply = getattr(raw, "_prime_entities_for_reply", None)
        if callable(prime_for_reply):
            await prime_for_reply(want=Peer.channel(int(peer_id)), timeout=self.timeout)
            await prime_for_reply(want=Peer.user(int(user_id)), timeout=self.timeout)
            return
        prime = getattr(raw, "prime_entities", None)
        if callable(prime):
            try:
                await prime(limit=200, timeout=self.timeout)
            except TypeError:
                await prime()

    async def send_audit(self, text: str) -> None:
        peer = self.config.audit_peer
        if not isinstance(peer, str) or not peer.strip():
            return
        try:
            await self.app.messages.send(peer.strip(), text, timeout=self.timeout)
        except Exception as ex:  # noqa: BLE001
            logger.info("audit send failed: %s", ex)

    def track_flood(self, *, peer_key: str, user_id: int, now: float | None = None) -> int:
        ts = time.monotonic() if now is None else float(now)
        key = (peer_key, int(user_id))
        bucket = self._flood_events.get(key)
        if bucket is None:
            bucket = deque()
            self._flood_events[key] = bucket
        window = max(1.0, float(self.config.flood_window_seconds))
        while bucket and (ts - bucket[0]) > window:
            bucket.popleft()
        bucket.append(ts)
        return len(bucket)

    def flood_on_cooldown(self, *, peer_key: str, user_id: int, now: float | None = None) -> bool:
        ts = time.monotonic() if now is None else float(now)
        key = (peer_key, int(user_id))
        last = self._flood_last_action.get(key)
        if last is None:
            return False
        return (ts - last) < float(max(1, self.config.flood_cooldown_seconds))

    def mark_flood_action(self, *, peer_key: str, user_id: int, now: float | None = None) -> None:
        ts = time.monotonic() if now is None else float(now)
        self._flood_last_action[(peer_key, int(user_id))] = ts

    def reset_scheduled_runtime(self) -> None:
        self.scheduled_names.clear()

    async def ensure_schedule(self, job: ScheduledJobRecord) -> None:
        if not job.enabled:
            return
        if job.name in self.scheduled_names:
            return
        interval = int(job.interval_seconds)
        if interval <= 0:
            return

        async def _runner() -> None:
            peer = job.peer_ref
            if peer is None:
                if self.allowed_peer_keys:
                    peer = sorted(self.allowed_peer_keys)[0]
                elif self.config.allowed_peers:
                    peer = self.config.allowed_peers[0]
            if peer is None:
                return
            await self.app.messages.send(peer, job.text, timeout=self.timeout)
            self.storage.touch_scheduled_job(name=job.name)

        self.scheduler.every(
            interval_seconds=float(interval),
            fn=_runner,
            name=f"announcement:{job.name}",
            run_immediately=False,
        )
        self.scheduled_names.add(job.name)

    async def register_or_update_schedule(
        self,
        *,
        name: str,
        text: str,
        interval_seconds: int,
        peer_ref: str | None,
        enabled: bool = True,
    ) -> None:
        self.storage.upsert_scheduled_job(
            name=name,
            text=text,
            interval_seconds=interval_seconds,
            peer_ref=peer_ref,
            enabled=enabled,
        )
        jobs = self.storage.list_scheduled_jobs(enabled_only=True)
        for job in jobs:
            if job.name == name:
                await self.ensure_schedule(job)
                break


def attach_group_bot_context(router: Router, ctx: GroupBotContext) -> None:
    setattr(router, _CONTEXT_ATTR, ctx)


def get_group_bot_context(router: Router) -> GroupBotContext:
    obj = getattr(router, _CONTEXT_ATTR, None)
    if isinstance(obj, GroupBotContext):
        return obj
    raise RuntimeError("Group bot context is not attached to Router")


def parse_peer_key(raw: str) -> str | None:
    s = raw.strip()
    m = _PEER_KEY_RE.match(s)
    if m is None:
        return None
    return f"{m.group(1)}:{int(m.group(2))}"


def cast_maybe_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def cast_maybe_int(value: Any) -> int | None:
    return int(value) if isinstance(value, int) else None
