from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from telecraft.bot.events import MessageEvent
from telecraft.bot.filters import Filter, all_

Handler = Callable[[MessageEvent], Awaitable[None]]

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _MessageHandler:
    filt: Filter
    fn: Handler


class Router:
    def __init__(self) -> None:
        self._message_handlers: list[_MessageHandler] = []

    def on_message(self, filt: Filter | None = None) -> Callable[[Handler], Handler]:
        """
        Decorator:
          @router.on_message(filters.text())
          async def handler(e): ...

        Tips:
        - Use richer event fields: e.sender_id / e.peer_type / e.peer_id
        - Useful filters live in telecraft.bot (or telecraft.bot.filters), e.g.:
            private(), group(), channel(), from_user(...), in_chat(...), regex(...)
        """

        f = filt or all_()

        def _decorator(fn: Handler) -> Handler:
            self._message_handlers.append(_MessageHandler(filt=f, fn=fn))
            return fn

        return _decorator

    async def dispatch_message(self, e: MessageEvent) -> None:
        for h in self._message_handlers:
            try:
                if not h.filt(e):
                    continue
                await h.fn(e)
            except Exception as ex:  # noqa: BLE001
                logger.exception("Handler crashed", exc_info=ex)

