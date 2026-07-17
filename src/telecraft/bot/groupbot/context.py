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

from .config import GroupBotConfig, validate_group_bot_config
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
            return bool(self.config.allow_all_peers)
        key = self.peer_key(peer_type, peer_id)
        if key is None:
            return False
        return key in self.allowed_peer_keys

    async def resolve_allowed_peer_keys(self) -> set[str]:
        validate_group_bot_config(self.config)
        refs = list(self.config.allowed_peers)
        if self.config.allow_all_peers:
            self.allowed_peer_keys = set()
            return set()
        out: set[str] = set()
        unresolved: list[str] = []
        for ref in refs:
            parsed = parse_peer_key(ref)
            if parsed is not None:
                out.add(parsed)
                continue
            try:
                peer = await self.app.raw.resolve_peer(ref, timeout=self.timeout)
            except Exception as ex:  # noqa: BLE001
                logger.warning("Failed to resolve allowed peer %r: %s", ref, ex)
                unresolved.append(ref)
                continue
            key = self.peer_key(peer.peer_type, peer.peer_id)
            if key is not None:
                out.add(key)
            else:
                unresolved.append(ref)
        if unresolved:
            raise RuntimeError(
                "failed to resolve configured allowed_peers: "
                + ", ".join(repr(ref) for ref in unresolved)
            )
        self.allowed_peer_keys = out
        return set(out)

    def get_peer_read_only(self, peer_key: str | None) -> bool:
        default = bool(self.config.read_only_mode)
        if peer_key is None:
            return default
        value = self.storage.get_group_setting(
            peer_key=peer_key,
            key="read_only_mode",
            default=default,
        )
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "y", "on"}:
                return True
            if normalized in {"0", "false", "no", "n", "off"}:
                return False
            return default
        if isinstance(value, (int, float)):
            if value == 1:
                return True
            if value == 0:
                return False
            return default
        return default

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
        elif peer_type == "chat" and peer_id is not None:
            try:
                info = await self.app.profile.chat_info(
                    f"chat:{int(peer_id)}",
                    timeout=self.timeout,
                )
                full_chat = getattr(info, "full_chat", None)
                participants_obj = getattr(full_chat, "participants", None)
                participants = getattr(participants_obj, "participants", [])
                for participant in participants if isinstance(participants, list) else []:
                    participant_user_id = cast_maybe_int(getattr(participant, "user_id", None))
                    if participant_user_id != uid:
                        continue
                    name = str(getattr(participant, "TL_NAME", "")).lower()
                    is_admin = any(token in name for token in ("admin", "creator"))
                    break
            except Exception as ex:  # noqa: BLE001
                should_cache = False
                logger.info("is_admin basic-chat lookup failed peer=%s user=%s: %s", key, uid, ex)

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

    async def _resolve_scheduled_peer(self, peer_ref: str | None) -> str:
        candidate = peer_ref.strip() if isinstance(peer_ref, str) and peer_ref.strip() else None
        if candidate is None:
            if self.allowed_peer_keys:
                candidate = sorted(self.allowed_peer_keys)[0]
            elif self.config.allowed_peers:
                candidate = self.config.allowed_peers[0]
            else:
                raise ValueError("scheduled jobs require an explicit peer in allow-all mode")

        key = parse_peer_key(candidate)
        if key is None:
            peer = await self.app.raw.resolve_peer(candidate, timeout=self.timeout)
            key = self.peer_key(peer.peer_type, peer.peer_id)
        if key is None:
            raise ValueError(f"scheduled job peer could not be resolved: {candidate!r}")
        peer_type, _, peer_id_raw = key.partition(":")
        if not self.is_peer_allowed(peer_type, int(peer_id_raw)):
            raise ValueError(f"scheduled job peer is outside allowed_peers: {key}")
        return key

    async def ensure_schedule(self, job: ScheduledJobRecord) -> bool:
        if not job.enabled or job.suppressed:
            return False
        if job.name in self.scheduled_names:
            return True
        interval = int(job.interval_seconds)
        if interval <= 0:
            self.storage.set_scheduled_job_state(
                name=job.name,
                enabled=False,
                suppressed=job.suppressed,
            )
            logger.error("Scheduled job disabled with invalid interval (job=%s)", job.name)
            return False

        try:
            peer_key = await self._resolve_scheduled_peer(job.peer_ref)
        except Exception as ex:  # noqa: BLE001
            self.storage.set_scheduled_job_state(
                name=job.name,
                enabled=False,
                suppressed=job.suppressed,
            )
            logger.error("Scheduled job disabled (job=%s): %s", job.name, ex)
            return False

        async def _runner() -> None:
            peer_type, _, peer_id_raw = peer_key.partition(":")
            if not self.is_peer_allowed(peer_type, int(peer_id_raw)):
                logger.error(
                    "Scheduled job blocked outside allowed scope (job=%s peer=%s)",
                    job.name,
                    peer_key,
                )
                return
            if self.get_peer_read_only(peer_key):
                logger.info(
                    "Scheduled job skipped in read-only mode (job=%s peer=%s)",
                    job.name,
                    peer_key,
                )
                return
            await self.app.messages.send(peer_key, job.text, timeout=self.timeout)
            self.storage.touch_scheduled_job(name=job.name)

        self.scheduler.every(
            interval_seconds=float(interval),
            fn=_runner,
            name=f"announcement:{job.name}",
            run_immediately=False,
        )
        self.scheduled_names.add(job.name)
        return True

    async def register_or_update_schedule(
        self,
        *,
        name: str,
        text: str,
        interval_seconds: int,
        peer_ref: str | None,
        enabled: bool = True,
    ) -> None:
        normalized_name = str(name).strip()
        normalized_text = str(text).strip()
        normalized_interval = int(interval_seconds)
        if not normalized_name:
            raise ValueError("scheduled job name must not be empty")
        if not normalized_text:
            raise ValueError("scheduled job text must not be empty")
        if normalized_interval <= 0:
            raise ValueError("scheduled job interval_seconds must be greater than zero")
        canonical_peer = await self._resolve_scheduled_peer(peer_ref)
        await self.scheduler.cancel(f"announcement:{normalized_name}")
        self.scheduled_names.discard(normalized_name)
        self.storage.upsert_scheduled_job(
            name=normalized_name,
            text=normalized_text,
            interval_seconds=normalized_interval,
            peer_ref=canonical_peer,
            enabled=enabled,
            source="manual",
            suppressed=False,
        )
        job = self.storage.get_scheduled_job(name=normalized_name)
        if job is not None:
            await self.ensure_schedule(job)

    async def list_schedules_for_peer(self, peer_ref: str) -> list[ScheduledJobRecord]:
        peer_key = await self._resolve_scheduled_peer(peer_ref)
        out: list[ScheduledJobRecord] = []
        for job in self.storage.list_scheduled_jobs(enabled_only=False):
            try:
                job_peer_key = await self._resolve_scheduled_peer(job.peer_ref)
            except Exception as ex:  # noqa: BLE001
                logger.warning("Skipping unresolved scheduled job %r: %s", job.name, ex)
                continue
            if job_peer_key == peer_key:
                out.append(job)
        return out

    async def remove_schedule(self, name: str, *, peer_ref: str | None = None) -> bool:
        job_name = str(name).strip()
        if not job_name:
            return False
        job = self.storage.get_scheduled_job(name=job_name)
        if job is None:
            return False
        if peer_ref is not None:
            expected_peer_key = await self._resolve_scheduled_peer(peer_ref)
            try:
                job_peer_key = await self._resolve_scheduled_peer(job.peer_ref)
            except Exception as ex:  # noqa: BLE001
                logger.warning("Refusing to remove unresolved scheduled job %r: %s", job_name, ex)
                return False
            if job_peer_key != expected_peer_key:
                return False
        if job is not None and job.source == "config":
            removed_storage = self.storage.set_scheduled_job_state(
                name=job_name,
                enabled=False,
                suppressed=True,
            )
        else:
            removed_storage = self.storage.delete_scheduled_job(name=job_name)
        self.scheduled_names.discard(job_name)
        removed_runtime = await self.scheduler.cancel(f"announcement:{job_name}")
        return bool(removed_storage or removed_runtime)


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
