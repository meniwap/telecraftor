from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Callable

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

    async def wait_for_message(
        self,
        *,
        filt: MessageFilter | None = None,
        timeout: float | None = None,
        consume: bool = True,
    ) -> MessageEvent:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[MessageEvent] = loop.create_future()
        waiter = _MessageWaiter(
            filt=filt or (lambda _e: True),
            future=future,
            consume=bool(consume),
        )
        self._waiters.append(waiter)
        try:
            if timeout is None:
                return await future
            return await asyncio.wait_for(future, timeout=float(timeout))
        finally:
            self._waiters = [w for w in self._waiters if w.future is not future]

    async def ask(
        self,
        event: MessageEvent,
        text: str,
        *,
        filt: MessageFilter | None = None,
        timeout: float | None = None,
        consume: bool = True,
        reply_kwargs: dict[str, Any] | None = None,
    ) -> MessageEvent:
        peer_type = event.peer_type
        peer_id = event.peer_id

        def _same_peer(e: MessageEvent) -> bool:
            return e.peer_type == peer_type and e.peer_id == peer_id

        if filt is None:
            composed = _same_peer
        else:
            composed = lambda e: _same_peer(e) and bool(filt(e))

        kwargs = dict(reply_kwargs or {})
        await event.reply(text, **kwargs)
        return await self.wait_for_message(
            filt=composed,
            timeout=timeout,
            consume=consume,
        )

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
