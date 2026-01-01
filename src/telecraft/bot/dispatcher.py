from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import Any

from telecraft.bot.events import (
    ChatActionEvent,
    DeletedMessagesEvent,
    MemberUpdateEvent,
    MessageEvent,
    ReactionEvent,
    parse_events,
)
from telecraft.bot.router import Router

logger = logging.getLogger(__name__)

_BacklogPolicy = str  # "ignore" | "process_no_reply" | "process_all"
_ThrottleMode = str  # "sleep" | "drop"

_ReactionDedupeKey = tuple[
    str,  # peer_type
    int,  # peer_id
    int,  # msg_id
    tuple[tuple[str, int], ...],  # sorted counts snapshot
    tuple[str, ...],  # sorted my_reactions snapshot
]


@dataclass(slots=True)
class _TokenBucket:
    rate_per_sec: float
    capacity: float
    tokens: float
    last_refill: float

    def refill(self, now: float) -> None:
        if self.rate_per_sec <= 0:
            return
        dt = now - self.last_refill
        if dt <= 0:
            return
        self.tokens = min(self.capacity, self.tokens + dt * self.rate_per_sec)
        self.last_refill = now

    def consume(self, now: float, amount: float = 1.0) -> float:
        """
        Consume tokens and return required delay (seconds) if we went below 0 tokens.
        """
        if self.rate_per_sec <= 0:
            return 0.0
        self.refill(now)
        self.tokens -= amount
        if self.tokens >= 0:
            return 0.0
        return (-self.tokens) / self.rate_per_sec


@dataclass(slots=True)
class Dispatcher:
    """
    Runs the bot loop:
    - reads raw updates from MtprotoClient.recv_update()
    - converts them to MessageEvent when possible
    - calls Router handlers with isolation (exceptions are logged, loop continues)
    """

    client: Any
    router: Router
    ignore_outgoing: bool = True
    ignore_before_start: bool = True
    backlog_grace_seconds: int = 10
    backlog_policy: _BacklogPolicy = "ignore"

    # Optional throttling (rate-limit event dispatch to handlers).
    throttle_global_per_minute: int | None = None
    throttle_peer_per_minute: int | None = None
    throttle_burst: int = 10
    throttle_max_delay_seconds: float = 1.0
    throttle_mode: _ThrottleMode = "sleep"  # "sleep" | "drop"
    # Optional debugging: log raw updates that match these rules (before parse_events).
    trace_update_names: tuple[str, ...] = ()
    trace_update_substrings: tuple[str, ...] = ()
    trace_all_updates: bool = False
    debug: bool = False

    async def run(self) -> None:
        started_at = int(time.time())
        # Dedupe messages by (peer_type, peer_id, msg_id, kind) to avoid duplicates while
        # still allowing edits to be processed.
        seen: set[tuple[str, int, int, str]] = set()
        seen_order: deque[tuple[str, int, int, str]] = deque(maxlen=4096)
        seen_other: set[tuple[str, str, int, int]] = set()
        seen_other_order: deque[tuple[str, str, int, int]] = deque(maxlen=4096)
        # Dedupe reactions by (peer, msg_id, counts snapshot, my_reactions snapshot).
        # This avoids dropping legit reaction changes on the same message while still
        # filtering duplicates caused by wrappers/replays.
        seen_reaction: set[_ReactionDedupeKey] = set()
        seen_reaction_order: deque[_ReactionDedupeKey] = deque(maxlen=4096)
        seen_member: set[tuple[str, int, int, str, int]] = set()
        seen_member_order: deque[tuple[str, int, int, str, int]] = deque(maxlen=4096)
        # Extra action dedupe by semantic signature within short time buckets
        # (helps for pin/title etc where Telegram can send multiple wrappers / duplicates).
        seen_action_sig: set[tuple[str, int, str, str, int]] = set()
        seen_action_sig_order: deque[tuple[str, int, str, str, int]] = deque(maxlen=4096)

        global_bucket: _TokenBucket | None = None
        peer_rate_per_sec: float | None = None
        peer_buckets: dict[tuple[str, int], _TokenBucket] = {}

        if self.throttle_global_per_minute is not None:
            r = float(self.throttle_global_per_minute) / 60.0
            if r > 0:
                now = time.monotonic()
                global_bucket = _TokenBucket(
                    rate_per_sec=r,
                    capacity=float(max(1, int(self.throttle_burst))),
                    tokens=float(max(1, int(self.throttle_burst))),
                    last_refill=now,
                )

        if self.throttle_peer_per_minute is not None:
            r2 = float(self.throttle_peer_per_minute) / 60.0
            if r2 > 0:
                peer_rate_per_sec = r2

        # Best-effort: populate access_hash cache (enables DM/channel replies).
        prime = getattr(self.client, "prime_entities", None)
        if callable(prime):
            try:
                await prime()
            except Exception as ex:  # noqa: BLE001
                logger.info("prime_entities failed; continuing without priming", exc_info=ex)

        await self.client.start_updates()
        while True:
            upd = await self.client.recv_update()
            now_ts = int(time.time())
            if self.trace_all_updates or self.trace_update_names or self.trace_update_substrings:
                name = getattr(upd, "TL_NAME", type(upd).__name__)
                should_trace = False
                if self.trace_all_updates:
                    should_trace = True
                elif isinstance(name, str):
                    if name in self.trace_update_names:
                        should_trace = True
                    else:
                        for sub in self.trace_update_substrings:
                            if sub and sub in name:
                                should_trace = True
                                break
                if should_trace:
                    extra = ""
                    if name == "messageService":
                        act = getattr(getattr(upd, "action", None), "TL_NAME", None)
                        extra = f" action={act}"
                    logger.info("[TRACE] update=%s%s", name, extra)
            evts = parse_events(client=self.client, update=upd)
            if not evts:
                if self.debug:
                    logger.info(
                        "Skip: unmapped update %s",
                        getattr(upd, "TL_NAME", type(upd).__name__),
                    )
                continue

            for evt in evts:
                if isinstance(evt, MessageEvent):
                    await self._handle_message(
                        evt,
                        started_at,
                        seen,
                        seen_order,
                        global_bucket,
                        peer_rate_per_sec,
                        peer_buckets,
                    )
                elif isinstance(evt, ChatActionEvent):
                    await self._handle_action(
                        evt,
                        started_at,
                        seen,
                        seen_order,
                        seen_action_sig,
                        seen_action_sig_order,
                        global_bucket,
                        peer_rate_per_sec,
                        peer_buckets,
                    )
                elif isinstance(evt, MemberUpdateEvent):
                    if not self._apply_backlog_policy(evt, started_at=started_at, now_ts=now_ts):
                        if self.debug:
                            logger.info(
                                "Skip: backlog policy drop member_update peer=%s:%s user=%s",
                                evt.peer_type,
                                evt.peer_id,
                                evt.user_id,
                            )
                        continue

                    pt = evt.peer_type or "unknown"
                    pid = int(evt.peer_id) if evt.peer_id is not None else 0
                    uid = int(evt.user_id) if evt.user_id is not None else 0
                    kind = str(getattr(evt, "kind", "update"))
                    key_id = int(evt.qts) if evt.qts is not None else int(evt.date or 0)
                    mkey = (pt, pid, uid, kind, key_id)
                    if mkey in seen_member:
                        continue
                    if len(seen_member_order) == seen_member_order.maxlen:
                        old_m = seen_member_order.popleft()
                        seen_member.discard(old_m)
                    seen_member_order.append(mkey)
                    seen_member.add(mkey)

                    if await self._maybe_throttle(
                        peer_type=evt.peer_type,
                        peer_id=evt.peer_id,
                        global_bucket=global_bucket,
                        peer_rate_per_sec=peer_rate_per_sec,
                        peer_buckets=peer_buckets,
                    ):
                        await self.router.dispatch_member_update(evt)
                elif isinstance(evt, ReactionEvent):
                    await self._handle_reaction(
                        evt,
                        started_at=started_at,
                        now_ts=now_ts,
                        seen_reaction=seen_reaction,
                        seen_reaction_order=seen_reaction_order,
                        global_bucket=global_bucket,
                        peer_rate_per_sec=peer_rate_per_sec,
                        peer_buckets=peer_buckets,
                    )
                elif isinstance(evt, DeletedMessagesEvent):
                    if not self._apply_backlog_policy(evt, started_at=started_at, now_ts=now_ts):
                        if self.debug:
                            logger.info(
                                "Skip: backlog policy drop delete ids=%s",
                                getattr(evt, "msg_ids", None),
                            )
                        continue
                    # Dedupe per message id, because a delete update can include many ids.
                    should_dispatch = False
                    for mid in evt.msg_ids:
                        if self._dedupe_other(
                            seen_other,
                            seen_other_order,
                            ("delete", evt.peer_type or "unknown", int(evt.peer_id or 0), int(mid)),
                        ):
                            should_dispatch = True
                    if should_dispatch:
                        if await self._maybe_throttle(
                            peer_type=evt.peer_type,
                            peer_id=evt.peer_id,
                            global_bucket=global_bucket,
                            peer_rate_per_sec=peer_rate_per_sec,
                            peer_buckets=peer_buckets,
                        ):
                            await self.router.dispatch_deleted_messages(evt)

    def _effective_backlog_policy(self) -> _BacklogPolicy:
        if not self.ignore_before_start:
            return "process_all"
        return self.backlog_policy

    def _is_backlog(self, *, date: int | None, started_at: int, now_ts: int | None = None) -> bool:
        """
        Determine whether an event should be considered backlog.

        - If the event has a Telegram `date`, we use it (classic behavior).
        - If the event has no `date` (common for reaction/delete updates), we treat updates that
          arrive right at startup as backlog for a short window. This prevents "bursty memories"
          from getDifference/reconnect from triggering replies immediately.
        """
        if date is None:
            if now_ts is None:
                return False
            # Startup window heuristic for undated updates.
            return now_ts <= (started_at + int(self.backlog_grace_seconds))
        return date < (started_at - int(self.backlog_grace_seconds))

    def _apply_backlog_policy(
        self, evt: Any, *, started_at: int, now_ts: int | None = None
    ) -> bool:
        """
        Returns True if event should continue to dispatch, False if it should be dropped.
        Also sets evt.is_backlog / evt.allow_reply when supported.
        """
        pol = self._effective_backlog_policy()
        date = getattr(evt, "date", None)
        is_backlog = self._is_backlog(date=date, started_at=started_at, now_ts=now_ts)
        if not is_backlog:
            return True

        # Mark the event (best-effort).
        try:
            setattr(evt, "is_backlog", True)
        except Exception:  # noqa: BLE001
            pass

        if pol == "ignore":
            return False
        if pol == "process_no_reply":
            try:
                setattr(evt, "allow_reply", False)
            except Exception:  # noqa: BLE001
                pass
            return True
        return True

    async def _maybe_throttle(
        self,
        *,
        peer_type: str | None,
        peer_id: int | None,
        global_bucket: _TokenBucket | None,
        peer_rate_per_sec: float | None,
        peer_buckets: dict[tuple[str, int], _TokenBucket],
    ) -> bool:
        """
        Returns True if event should be dispatched, False if dropped (throttle_mode='drop').
        """
        if global_bucket is None and peer_rate_per_sec is None:
            return True

        now = time.monotonic()
        delay = 0.0
        if global_bucket is not None:
            delay = max(delay, global_bucket.consume(now))

        if peer_rate_per_sec is not None:
            pt = peer_type or "unknown"
            pid = int(peer_id) if peer_id is not None else 0
            key = (pt, pid)
            b = peer_buckets.get(key)
            if b is None:
                # Best-effort guard against unbounded growth.
                if len(peer_buckets) >= 4096:
                    peer_buckets.clear()
                b = _TokenBucket(
                    rate_per_sec=peer_rate_per_sec,
                    capacity=float(max(1, int(self.throttle_burst))),
                    tokens=float(max(1, int(self.throttle_burst))),
                    last_refill=now,
                )
                peer_buckets[key] = b
            delay = max(delay, b.consume(now))

        if delay <= 0:
            return True

        if self.throttle_mode == "drop":
            if self.debug:
                logger.info(
                    "Drop: throttled event peer=%s:%s delay=%.3fs",
                    peer_type,
                    peer_id,
                    delay,
                )
            return False

        await asyncio.sleep(min(float(delay), float(self.throttle_max_delay_seconds)))
        return True

    def _dedupe_other(
        self,
        seen: set[tuple[str, str, int, int]],
        order: deque[tuple[str, str, int, int]],
        key: tuple[str, str, int, int],
    ) -> bool:
        if key in seen:
            return False
        if len(order) == order.maxlen:
            old = order.popleft()
            seen.discard(old)
        order.append(key)
        seen.add(key)
        return True

    async def _handle_reaction(
        self,
        evt: ReactionEvent,
        *,
        started_at: int,
        now_ts: int,
        seen_reaction: set[_ReactionDedupeKey],
        seen_reaction_order: deque[_ReactionDedupeKey],
        global_bucket: _TokenBucket | None,
        peer_rate_per_sec: float | None,
        peer_buckets: dict[tuple[str, int], _TokenBucket],
    ) -> None:
        if not self._apply_backlog_policy(evt, started_at=started_at, now_ts=now_ts):
            if self.debug:
                logger.info("Skip: backlog policy drop reaction msg_id=%s", evt.msg_id)
            return

        peer_type = evt.peer_type or "unknown"
        peer_id = int(evt.peer_id) if evt.peer_id is not None else 0

        # Allow repeated reaction updates for the same message as long as the snapshot differs.
        counts_sig = tuple(sorted(evt.counts.items()))
        my_sig = tuple(sorted(evt.my_reactions))
        key: _ReactionDedupeKey = (peer_type, peer_id, int(evt.msg_id), counts_sig, my_sig)
        if key in seen_reaction:
            return
        if len(seen_reaction_order) == seen_reaction_order.maxlen:
            old = seen_reaction_order.popleft()
            seen_reaction.discard(old)
        seen_reaction_order.append(key)
        seen_reaction.add(key)

        if await self._maybe_throttle(
            peer_type=evt.peer_type,
            peer_id=evt.peer_id,
            global_bucket=global_bucket,
            peer_rate_per_sec=peer_rate_per_sec,
            peer_buckets=peer_buckets,
        ):
            await self.router.dispatch_reaction(evt)

    async def _handle_message(
        self,
        evt: MessageEvent,
        started_at: int,
        seen: set[tuple[str, int, int, str]],
        seen_order: deque[tuple[str, int, int, str]],
        global_bucket: _TokenBucket | None,
        peer_rate_per_sec: float | None,
        peer_buckets: dict[tuple[str, int], _TokenBucket],
    ) -> None:
        # Never react to our own outgoing messages (prevents echo-loops).
        if self.ignore_outgoing and evt.outgoing:
            if self.debug:
                logger.info("Skip: outgoing message msg_id=%s", evt.msg_id)
            return

        if not self._apply_backlog_policy(evt, started_at=started_at, now_ts=int(time.time())):
            if self.debug:
                logger.info("Skip: backlog policy drop message date=%s", evt.date)
            return

        # Dedupe: sometimes the same message can arrive via different wrappers.
        peer_type = evt.peer_type or "unknown"
        peer_id = int(evt.peer_id) if evt.peer_id is not None else 0

        if evt.msg_id is not None:
            key = (peer_type, peer_id, int(evt.msg_id), str(getattr(evt, "kind", "new")))
            if key in seen:
                return
            if len(seen_order) == seen_order.maxlen:
                old = seen_order.popleft()
                seen.discard(old)
            seen_order.append(key)
            seen.add(key)

        if await self._maybe_throttle(
            peer_type=evt.peer_type,
            peer_id=evt.peer_id,
            global_bucket=global_bucket,
            peer_rate_per_sec=peer_rate_per_sec,
            peer_buckets=peer_buckets,
        ):
            await self.router.dispatch_message(evt)

    async def _handle_action(
        self,
        evt: ChatActionEvent,
        started_at: int,
        seen: set[tuple[str, int, int, str]],
        seen_order: deque[tuple[str, int, int, str]],
        seen_action_sig: set[tuple[str, int, str, str, int]],
        seen_action_sig_order: deque[tuple[str, int, str, str, int]],
        global_bucket: _TokenBucket | None,
        peer_rate_per_sec: float | None,
        peer_buckets: dict[tuple[str, int], _TokenBucket],
    ) -> None:
        # Never react to our own outgoing actions (prevents loops).
        if self.ignore_outgoing and evt.outgoing:
            if self.debug:
                logger.info("Skip: outgoing action kind=%s msg_id=%s", evt.kind, evt.msg_id)
            return

        if not self._apply_backlog_policy(evt, started_at=started_at, now_ts=int(time.time())):
            if self.debug:
                logger.info("Skip: backlog policy drop action date=%s", evt.date)
            return

        peer_type = evt.peer_type or "unknown"
        peer_id = int(evt.peer_id) if evt.peer_id is not None else 0

        # Extra semantic dedupe for action types that commonly duplicate across wrappers.
        # Important: do NOT collapse legitimate repeated actions (e.g. pin twice). If we have
        # a message id for the action, include it so each service message is distinct.
        detail: str | None = None
        if evt.kind == "pin":
            detail = f"pin:{int(evt.pinned_msg_id) if evt.pinned_msg_id is not None else 0}"
        elif evt.kind == "title":
            detail = f"title:{evt.new_title or ''}"
        elif evt.kind == "photo":
            detail = "photo"
        elif evt.kind == "join":
            detail = f"join:{int(evt.inviter_id) if evt.inviter_id is not None else 0}"
        elif evt.kind == "leave":
            detail = f"leave:{int(evt.removed_user_id) if evt.removed_user_id is not None else 0}"
        if detail is not None:
            if evt.msg_id is not None:
                key_id = int(evt.msg_id)
            else:
                # Undated/unidentified action: time-bucketed dedupe (~30s).
                bucket = int(time.time()) // 30
                key_id = -int(bucket) - 1
            sig = (peer_type, peer_id, str(evt.kind), detail, int(key_id))
            if sig in seen_action_sig:
                return
            if len(seen_action_sig_order) == seen_action_sig_order.maxlen:
                old_sig = seen_action_sig_order.popleft()
                seen_action_sig.discard(old_sig)
            seen_action_sig_order.append(sig)
            seen_action_sig.add(sig)

        if evt.msg_id is not None:
            key = (peer_type, peer_id, int(evt.msg_id), str(getattr(evt, "kind", "other")))
            if key in seen:
                return
            if len(seen_order) == seen_order.maxlen:
                old_msg = seen_order.popleft()
                seen.discard(old_msg)
            seen_order.append(key)
            seen.add(key)

        if await self._maybe_throttle(
            peer_type=evt.peer_type,
            peer_id=evt.peer_id,
            global_bucket=global_bucket,
            peer_rate_per_sec=peer_rate_per_sec,
            peer_buckets=peer_buckets,
        ):
            await self.router.dispatch_action(evt)

