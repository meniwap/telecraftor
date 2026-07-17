from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from telecraft.bot.events import (
    CallbackQueryEvent,
    ChatActionEvent,
    DeletedMessagesEvent,
    InlineQueryEvent,
    MemberUpdateEvent,
    MessageEvent,
    PrecheckoutQueryEvent,
    ReactionEvent,
    ShippingQueryEvent,
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
]

_DispatchFactory = Callable[[], Awaitable[None]]
_MessageSerialKey = tuple[str, int, int]


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


class _DispatchTaskPool:
    """Bound and supervise concurrent router dispatches."""

    def __init__(self, *, limit: int, max_pending: int = 4096) -> None:
        if int(limit) <= 0:
            raise ValueError("max_concurrent_handlers must be greater than zero")
        if int(max_pending) < int(limit):
            raise ValueError(
                "max_pending_handlers must be greater than or equal to max_concurrent_handlers"
            )
        self._semaphore = asyncio.Semaphore(int(limit))
        self._max_pending = int(max_pending)
        self._tasks: set[asyncio.Task[None]] = set()
        self._tails: dict[_MessageSerialKey, asyncio.Task[None]] = {}
        self._active_lane_tasks: dict[_MessageSerialKey, asyncio.Task[None]] = {}
        self._overflow_dropped = 0
        self._last_overflow_log_at = 0.0

    def schedule(
        self,
        factory: _DispatchFactory,
        *,
        label: str,
        serial_key: _MessageSerialKey | None = None,
    ) -> bool:
        # Queue without awaiting capacity here. A running handler may be
        # blocked in Router.ask(), so blocking the update loop would prevent it
        # from ingesting the answer that releases the handler. The semaphore
        # limits active handlers while queued events remain supervised tasks.
        # Conversation answers are routed before this method, so they remain
        # available even when the bounded pending queue is full.
        if len(self._tasks) >= self._max_pending:
            self._overflow_dropped += 1
            now = time.monotonic()
            if self._last_overflow_log_at == 0.0 or (now - self._last_overflow_log_at) >= 5.0:
                logger.warning(
                    "Drop: max pending handlers reached event=%s limit=%s dropped=%s",
                    label,
                    self._max_pending,
                    self._overflow_dropped,
                )
                self._overflow_dropped = 0
                self._last_overflow_log_at = now
            return False
        predecessor = self._tails.get(serial_key) if serial_key is not None else None
        task = asyncio.create_task(
            self._run_sequenced(
                predecessor,
                factory,
                label=label,
                serial_key=serial_key,
            ),
            name=f"telecraft-dispatch:{label}",
        )
        self._tasks.add(task)
        if serial_key is not None:
            self._tails[serial_key] = task

        def _on_done(done: asyncio.Task[None]) -> None:
            self._tasks.discard(done)
            if serial_key is not None and self._tails.get(serial_key) is done:
                self._tails.pop(serial_key, None)

        task.add_done_callback(_on_done)
        return True

    def lane_tail(self, serial_key: _MessageSerialKey) -> asyncio.Task[None] | None:
        return self._tails.get(serial_key)

    def active_lane_task(self, serial_key: _MessageSerialKey) -> asyncio.Task[None] | None:
        return self._active_lane_tasks.get(serial_key)

    async def _run_sequenced(
        self,
        predecessor: asyncio.Task[None] | None,
        factory: _DispatchFactory,
        *,
        label: str,
        serial_key: _MessageSerialKey | None,
    ) -> None:
        if predecessor is not None:
            # A handler may cancel itself. Treat that as completion of its lane
            # slot so already-queued messages from the same sender still run.
            # Cancelling this task (for example during pool.close()) still
            # propagates through gather and stops the queue promptly.
            await asyncio.gather(predecessor, return_exceptions=True)
        async with self._semaphore:
            current = asyncio.current_task()
            if serial_key is not None and current is not None:
                self._active_lane_tasks[serial_key] = current
            try:
                await self._run_isolated(factory, label=label)
            finally:
                if (
                    serial_key is not None
                    and current is not None
                    and self._active_lane_tasks.get(serial_key) is current
                ):
                    self._active_lane_tasks.pop(serial_key, None)

    async def _run_isolated(self, factory: _DispatchFactory, *, label: str) -> None:
        try:
            await factory()
        except asyncio.CancelledError:
            raise
        except Exception as ex:  # noqa: BLE001
            logger.error(
                "Event dispatch crashed event=%s",
                label,
                exc_info=(type(ex), ex, ex.__traceback__),
            )

    async def close(self, *, timeout: float | None = 30.0) -> None:
        tasks = tuple(self._tasks)
        if tasks:
            if timeout is None:
                _done, pending = await asyncio.wait(tasks)
            else:
                _done, pending = await asyncio.wait(
                    tasks,
                    timeout=max(0.0, float(timeout)),
                )
            if pending:
                logger.error(
                    "Handler drain timed out; cancelling pending handlers count=%s",
                    len(pending),
                )
                for task in pending:
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()
        self._tails.clear()
        self._active_lane_tasks.clear()

    def cancel(self) -> None:
        for task in tuple(self._tasks):
            task.cancel()


@dataclass(slots=True)
class Dispatcher:
    """
    Runs the bot loop:
    - reads raw updates from MtprotoClient.recv_update()
    - converts them to MessageEvent when possible
    - calls Router handlers with isolation (exceptions are logged, loop continues)
    - preserves message order for each sender within a peer while allowing
      independent lanes to run concurrently up to max_concurrent_handlers
    - queues excess message handlers up to max_pending_handlers; pending
      conversation answers bypass the handler queue so an ask() cannot deadlock
      update ingestion
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
    # Appended for positional-constructor compatibility with earlier releases.
    max_concurrent_handlers: int = 1
    max_pending_handlers: int = 4096
    handler_shutdown_timeout_seconds: float = 30.0

    async def run(self) -> None:
        self.router.open_conversations()
        dispatch_pool = _DispatchTaskPool(
            limit=self.max_concurrent_handlers,
            max_pending=self.max_pending_handlers,
        )
        try:
            await self._run(dispatch_pool=dispatch_pool)
        finally:
            # No new updates can arrive after _run exits. Abort handlers that
            # are waiting for a conversation answer, then drain all accepted
            # message work before reconnect so persisted update state cannot
            # advance past handlers that never ran.
            self.router.close_conversations()
            await dispatch_pool.close(timeout=self.handler_shutdown_timeout_seconds)
            self.router.clear_buffered_conversations()

    async def _run(self, *, dispatch_pool: _DispatchTaskPool) -> None:
        started_at = int(time.time())
        # Dedupe messages by (peer_type, peer_id, msg_id, kind) to avoid duplicates while
        # still allowing edits to be processed.
        seen: set[tuple[str, int, int, str]] = set()
        seen_order: deque[tuple[str, int, int, str]] = deque(maxlen=4096)
        seen_other: set[tuple[str, str, int, int]] = set()
        seen_other_order: deque[tuple[str, str, int, int]] = deque(maxlen=4096)
        # Dedupe reactions by (peer, msg_id, counts snapshot).
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

        # Best-effort: identify "me" (helps classify self-authored messages in Saved Messages).
        me: Any | None = None
        get_me = getattr(self.client, "get_me", None)
        if callable(get_me):
            try:
                me = await get_me()
            except Exception as ex:  # noqa: BLE001
                logger.info("get_me failed; continuing without self identity", exc_info=ex)

        # Best-effort: populate access_hash cache (enables DM/channel replies).
        prime = getattr(self.client, "prime_entities", None)
        # Telegram rejects dialogs.getDialogs for bot authorizations with
        # BOT_METHOD_INVALID, which is what prime_entities uses. Bot entity
        # caches are hydrated from incoming updates instead.
        if callable(prime) and not bool(getattr(me, "bot", False)):
            try:
                await prime()
            except Exception as ex:  # noqa: BLE001
                logger.info("prime_entities failed; continuing without priming", exc_info=ex)

        # Message handlers run in background tasks and share this turnstile so
        # sleep-mode throttling remains staggered. Event types dispatched
        # inline deliberately do not wait behind that handler backlog, keeping
        # update ingestion responsive under load.
        message_throttle_lock = asyncio.Lock()

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
                        dispatch_pool,
                        message_throttle_lock,
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
                elif isinstance(evt, CallbackQueryEvent):
                    await self._handle_callback(
                        evt,
                        started_at=started_at,
                        now_ts=now_ts,
                        seen_other=seen_other,
                        seen_other_order=seen_other_order,
                        global_bucket=global_bucket,
                        peer_rate_per_sec=peer_rate_per_sec,
                        peer_buckets=peer_buckets,
                    )
                elif isinstance(evt, InlineQueryEvent):
                    await self._handle_inline_query(
                        evt,
                        started_at=started_at,
                        now_ts=now_ts,
                        seen_other=seen_other,
                        seen_other_order=seen_other_order,
                        global_bucket=global_bucket,
                        peer_rate_per_sec=peer_rate_per_sec,
                        peer_buckets=peer_buckets,
                    )
                elif isinstance(evt, ShippingQueryEvent):
                    await self._handle_shipping_query(
                        evt,
                        started_at=started_at,
                        now_ts=now_ts,
                        seen_other=seen_other,
                        seen_other_order=seen_other_order,
                        global_bucket=global_bucket,
                        peer_rate_per_sec=peer_rate_per_sec,
                        peer_buckets=peer_buckets,
                    )
                elif isinstance(evt, PrecheckoutQueryEvent):
                    await self._handle_precheckout_query(
                        evt,
                        started_at=started_at,
                        now_ts=now_ts,
                        seen_other=seen_other,
                        seen_other_order=seen_other_order,
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
        throttle_lock: asyncio.Lock | None = None,
    ) -> bool:
        """
        Returns True if event should be dispatched, False if dropped (throttle_mode='drop').
        """
        if global_bucket is None and peer_rate_per_sec is None:
            return True

        if throttle_lock is not None:
            async with throttle_lock:
                return await self._maybe_throttle(
                    peer_type=peer_type,
                    peer_id=peer_id,
                    global_bucket=global_bucket,
                    peer_rate_per_sec=peer_rate_per_sec,
                    peer_buckets=peer_buckets,
                )

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
        throttle_lock: asyncio.Lock | None = None,
    ) -> None:
        if not self._apply_backlog_policy(evt, started_at=started_at, now_ts=now_ts):
            if self.debug:
                logger.info("Skip: backlog policy drop reaction msg_id=%s", evt.msg_id)
            return

        peer_type = evt.peer_type or "unknown"
        peer_id = int(evt.peer_id) if evt.peer_id is not None else 0

        # Allow repeated reaction updates for the same message as long as counts differs.
        #
        # Note: we intentionally do NOT include `my_reactions` in the dedupe key. Telegram can
        # deliver two updates for the same reaction change (updateMessageReactions + edit-wrapper)
        # where only one includes "recent_reactions"/"my" info. Including it causes double-dispatch.
        counts_sig = tuple(sorted(evt.counts.items()))
        key: _ReactionDedupeKey = (peer_type, peer_id, int(evt.msg_id), counts_sig)
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
            throttle_lock=throttle_lock,
        ):
            await self.router.dispatch_reaction(evt)

    async def _handle_callback(
        self,
        evt: CallbackQueryEvent,
        *,
        started_at: int,
        now_ts: int,
        seen_other: set[tuple[str, str, int, int]],
        seen_other_order: deque[tuple[str, str, int, int]],
        global_bucket: _TokenBucket | None,
        peer_rate_per_sec: float | None,
        peer_buckets: dict[tuple[str, int], _TokenBucket],
        throttle_lock: asyncio.Lock | None = None,
    ) -> None:
        if not self._apply_backlog_policy(evt, started_at=started_at, now_ts=now_ts):
            if self.debug:
                logger.info("Skip: backlog policy drop callback query_id=%s", evt.query_id)
            return

        if not self._dedupe_other(
            seen_other,
            seen_other_order,
            (
                "callback",
                evt.peer_type or "unknown",
                int(evt.peer_id or 0),
                int(evt.query_id),
            ),
        ):
            return

        if await self._maybe_throttle(
            peer_type=evt.peer_type,
            peer_id=evt.peer_id,
            global_bucket=global_bucket,
            peer_rate_per_sec=peer_rate_per_sec,
            peer_buckets=peer_buckets,
            throttle_lock=throttle_lock,
        ):
            await self.router.dispatch_callback_query(evt)

    async def _handle_inline_query(
        self,
        evt: InlineQueryEvent,
        *,
        started_at: int,
        now_ts: int,
        seen_other: set[tuple[str, str, int, int]],
        seen_other_order: deque[tuple[str, str, int, int]],
        global_bucket: _TokenBucket | None,
        peer_rate_per_sec: float | None,
        peer_buckets: dict[tuple[str, int], _TokenBucket],
        throttle_lock: asyncio.Lock | None = None,
    ) -> None:
        if not self._apply_backlog_policy(evt, started_at=started_at, now_ts=now_ts):
            if self.debug:
                logger.info("Skip: backlog policy drop inline query_id=%s", evt.query_id)
            return

        if not self._dedupe_other(
            seen_other,
            seen_other_order,
            ("inline_query", "query", 0, int(evt.query_id)),
        ):
            return

        if await self._maybe_throttle(
            peer_type="user",
            peer_id=evt.user_id,
            global_bucket=global_bucket,
            peer_rate_per_sec=peer_rate_per_sec,
            peer_buckets=peer_buckets,
            throttle_lock=throttle_lock,
        ):
            await self.router.dispatch_inline_query(evt)

    async def _handle_shipping_query(
        self,
        evt: ShippingQueryEvent,
        *,
        started_at: int,
        now_ts: int,
        seen_other: set[tuple[str, str, int, int]],
        seen_other_order: deque[tuple[str, str, int, int]],
        global_bucket: _TokenBucket | None,
        peer_rate_per_sec: float | None,
        peer_buckets: dict[tuple[str, int], _TokenBucket],
        throttle_lock: asyncio.Lock | None = None,
    ) -> None:
        if not self._apply_backlog_policy(evt, started_at=started_at, now_ts=now_ts):
            if self.debug:
                logger.info("Skip: backlog policy drop shipping query_id=%s", evt.query_id)
            return

        if not self._dedupe_other(
            seen_other,
            seen_other_order,
            ("shipping_query", "query", 0, int(evt.query_id)),
        ):
            return

        if await self._maybe_throttle(
            peer_type="user",
            peer_id=evt.user_id,
            global_bucket=global_bucket,
            peer_rate_per_sec=peer_rate_per_sec,
            peer_buckets=peer_buckets,
            throttle_lock=throttle_lock,
        ):
            await self.router.dispatch_shipping_query(evt)

    async def _handle_precheckout_query(
        self,
        evt: PrecheckoutQueryEvent,
        *,
        started_at: int,
        now_ts: int,
        seen_other: set[tuple[str, str, int, int]],
        seen_other_order: deque[tuple[str, str, int, int]],
        global_bucket: _TokenBucket | None,
        peer_rate_per_sec: float | None,
        peer_buckets: dict[tuple[str, int], _TokenBucket],
        throttle_lock: asyncio.Lock | None = None,
    ) -> None:
        if not self._apply_backlog_policy(evt, started_at=started_at, now_ts=now_ts):
            if self.debug:
                logger.info("Skip: backlog policy drop precheckout query_id=%s", evt.query_id)
            return

        if not self._dedupe_other(
            seen_other,
            seen_other_order,
            ("precheckout_query", "query", 0, int(evt.query_id)),
        ):
            return

        if await self._maybe_throttle(
            peer_type="user",
            peer_id=evt.user_id,
            global_bucket=global_bucket,
            peer_rate_per_sec=peer_rate_per_sec,
            peer_buckets=peer_buckets,
            throttle_lock=throttle_lock,
        ):
            await self.router.dispatch_precheckout_query(evt)

    async def _handle_message(
        self,
        evt: MessageEvent,
        started_at: int,
        seen: set[tuple[str, int, int, str]],
        seen_order: deque[tuple[str, int, int, str]],
        global_bucket: _TokenBucket | None,
        peer_rate_per_sec: float | None,
        peer_buckets: dict[tuple[str, int], _TokenBucket],
        dispatch_pool: _DispatchTaskPool | None = None,
        throttle_lock: asyncio.Lock | None = None,
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

        # Conversation answers must bypass the bounded handler pool. Otherwise
        # a pool filled with handlers waiting in Router.ask() could deadlock on
        # the very messages that release those handlers.
        if self.router.feed_conversation_message(evt):
            return

        serial_key = (peer_type, peer_id, int(evt.sender_id or 0))
        active_predecessor = (
            dispatch_pool.active_lane_task(serial_key) if dispatch_pool is not None else None
        )
        # The previous handler may not have registered ask() yet. Buffer this
        # already-ingested message so that a waiter opened by that handler can
        # claim it without breaking per-sender ordering.
        buffered = bool(
            active_predecessor is not None and self.router.buffer_conversation_message(evt)
        )

        async def _dispatch() -> None:
            if buffered and self.router.finish_buffered_conversation_message(evt):
                return
            allowed = await self._maybe_throttle(
                peer_type=evt.peer_type,
                peer_id=evt.peer_id,
                global_bucket=global_bucket,
                peer_rate_per_sec=peer_rate_per_sec,
                peer_buckets=peer_buckets,
                throttle_lock=throttle_lock,
            )
            if allowed:
                await self.router.dispatch_message_handlers(evt)

        if dispatch_pool is None:
            await _dispatch()
            return

        scheduled = dispatch_pool.schedule(
            _dispatch,
            label=f"message:{peer_type}:{peer_id}:{int(evt.msg_id or 0)}",
            serial_key=serial_key,
        )
        if buffered and active_predecessor is not None:
            if scheduled:
                # Once the active handler exits it can no longer open a waiter.
                # A claimed message stays marked until its queued dispatch
                # observes the claim and skips regular handlers.
                active_predecessor.add_done_callback(
                    lambda _done: self.router.discard_buffered_conversation_message(evt)
                )
            else:
                # If overload drops the regular handler there is no queued
                # dispatch to clear a claimed marker, so finish it here.
                active_predecessor.add_done_callback(
                    lambda _done: self.router.finish_buffered_conversation_message(evt)
                )

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
        throttle_lock: asyncio.Lock | None = None,
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
            throttle_lock=throttle_lock,
        ):
            await self.router.dispatch_action(evt)
