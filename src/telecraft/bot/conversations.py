from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from telecraft.bot.events import MessageEvent

MessageFilter = Callable[[MessageEvent], bool]


@dataclass(slots=True)
class _MessageWaiter:
    filt: MessageFilter
    future: asyncio.Future[MessageEvent]
    consume: bool


class ConversationManager:
    def __init__(self) -> None:
        self._waiters: list[_MessageWaiter] = []
        self._buffered_messages: list[MessageEvent] = []
        self._claimed_buffered_ids: set[int] = set()
        self._accepting_waiters = True

    def open(self) -> None:
        self._accepting_waiters = True

    def close(self) -> None:
        self._accepting_waiters = False
        for waiter in self._waiters:
            if not waiter.future.done():
                waiter.future.cancel()
        self._waiters.clear()

    def clear_buffered(self) -> None:
        self._buffered_messages.clear()
        self._claimed_buffered_ids.clear()

    def buffer_message(self, event: MessageEvent) -> None:
        if any(item is event for item in self._buffered_messages):
            return
        if len(self._buffered_messages) >= 4096:
            self._buffered_messages.pop(0)
        self._buffered_messages.append(event)

    def finish_buffered_message(self, event: MessageEvent) -> bool:
        """Remove a queued message and report whether a waiter consumed it."""
        self._buffered_messages = [item for item in self._buffered_messages if item is not event]
        event_id = id(event)
        if event_id not in self._claimed_buffered_ids:
            return False
        self._claimed_buffered_ids.discard(event_id)
        return True

    def discard_buffered_message(self, event: MessageEvent) -> None:
        """Stop offering an unclaimed message to future conversation waiters."""
        self._buffered_messages = [item for item in self._buffered_messages if item is not event]

    def _resolve_waiter_from_buffer(self, waiter: _MessageWaiter) -> None:
        for index, event in enumerate(self._buffered_messages):
            try:
                matched = bool(waiter.filt(event))
            except Exception:  # noqa: BLE001
                matched = False
            if not matched:
                continue
            self._buffered_messages.pop(index)
            waiter.future.set_result(event)
            if waiter.consume:
                self._claimed_buffered_ids.add(id(event))
            return

    def _register_waiter(
        self,
        *,
        filt: MessageFilter | None,
        consume: bool,
    ) -> _MessageWaiter:
        if not self._accepting_waiters:
            raise RuntimeError("conversation manager is closed")
        loop = asyncio.get_running_loop()
        waiter = _MessageWaiter(
            filt=filt or (lambda _e: True),
            future=loop.create_future(),
            consume=bool(consume),
        )
        self._waiters.append(waiter)
        self._resolve_waiter_from_buffer(waiter)
        return waiter

    def _remove_waiter(self, waiter: _MessageWaiter) -> None:
        self._waiters = [item for item in self._waiters if item is not waiter]

    async def _wait_for_registered(
        self,
        waiter: _MessageWaiter,
        *,
        timeout: float | None,
    ) -> MessageEvent:
        try:
            if timeout is None:
                return await waiter.future
            return await asyncio.wait_for(waiter.future, timeout=float(timeout))
        finally:
            self._remove_waiter(waiter)

    async def wait_for_message(
        self,
        *,
        filt: MessageFilter | None = None,
        timeout: float | None = None,
        consume: bool = True,
    ) -> MessageEvent:
        waiter = self._register_waiter(filt=filt, consume=consume)
        return await self._wait_for_registered(waiter, timeout=timeout)

    async def ask(
        self,
        event: MessageEvent,
        text: str,
        *,
        filt: MessageFilter | None = None,
        timeout: float | None = None,
        consume: bool = True,
        same_sender: bool = False,
        reply_kwargs: dict[str, Any] | None = None,
    ) -> MessageEvent:
        peer_type = event.peer_type
        peer_id = event.peer_id
        sender_id = event.sender_id

        def _same_conversation(e: MessageEvent) -> bool:
            if e.peer_type != peer_type or e.peer_id != peer_id:
                return False
            if not same_sender:
                return True
            return e.sender_id == sender_id

        if filt is None:
            composed = _same_conversation
        else:

            def composed(e: MessageEvent) -> bool:
                return _same_conversation(e) and bool(filt(e))

        # Register before sending the prompt. The update loop keeps ingesting
        # while the send RPC is in flight, so registering afterwards can miss a
        # fast answer that arrives before Telegram acknowledges the prompt.
        waiter = self._register_waiter(filt=composed, consume=consume)
        try:
            kwargs = dict(reply_kwargs or {})
            await event.reply(text, **kwargs)
        except BaseException:
            self._remove_waiter(waiter)
            if not waiter.future.done():
                waiter.future.cancel()
            raise
        return await self._wait_for_registered(waiter, timeout=timeout)

    def feed_message(self, event: MessageEvent) -> bool:
        if not self._waiters:
            return False

        consumed = False
        remaining: list[_MessageWaiter] = []
        for waiter in self._waiters:
            if waiter.future.done():
                continue
            matched = False
            try:
                matched = bool(waiter.filt(event))
            except Exception:  # noqa: BLE001
                matched = False
            if matched and not waiter.future.done():
                waiter.future.set_result(event)
                consumed = consumed or waiter.consume
                continue
            remaining.append(waiter)

        self._waiters = remaining
        return consumed
