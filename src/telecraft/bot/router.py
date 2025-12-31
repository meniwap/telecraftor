from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from telecraft.bot.events import DeletedMessagesEvent, MessageEvent, ReactionEvent
from telecraft.bot.exceptions import StopPropagation
from telecraft.bot.filters import Filter, all_

Handler = Callable[[MessageEvent], Awaitable[None]]
ReactionHandler = Callable[[ReactionEvent], Awaitable[None]]
DeletedHandler = Callable[[DeletedMessagesEvent], Awaitable[None]]

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _MessageHandler:
    filt: Filter
    fn: Handler
    stop: bool = False


@dataclass(slots=True)
class _ReactionHandler:
    filt: Callable[[ReactionEvent], bool]
    fn: ReactionHandler
    stop: bool = False


@dataclass(slots=True)
class _DeletedHandler:
    filt: Callable[[DeletedMessagesEvent], bool]
    fn: DeletedHandler
    stop: bool = False


class Router:
    def __init__(self) -> None:
        self._message_handlers: list[_MessageHandler] = []
        self._reaction_handlers: list[_ReactionHandler] = []
        self._deleted_handlers: list[_DeletedHandler] = []

    def on_message(
        self, filt: Filter | None = None, *, stop: bool = False
    ) -> Callable[[Handler], Handler]:
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
            self._message_handlers.append(_MessageHandler(filt=f, fn=fn, stop=stop))
            return fn

        return _decorator

    async def dispatch_message(self, e: MessageEvent) -> None:
        for h in self._message_handlers:
            try:
                if not h.filt(e):
                    continue
                await h.fn(e)
                if h.stop:
                    break
            except StopPropagation:
                break
            except Exception as ex:  # noqa: BLE001
                logger.exception("Handler crashed", exc_info=ex)

    def on_reaction(
        self,
        filt: Callable[[ReactionEvent], bool] | None = None,
        *,
        stop: bool = False,
    ) -> Callable[[ReactionHandler], ReactionHandler]:
        f = filt or (lambda _e: True)

        def _decorator(fn: ReactionHandler) -> ReactionHandler:
            self._reaction_handlers.append(_ReactionHandler(filt=f, fn=fn, stop=stop))
            return fn

        return _decorator

    async def dispatch_reaction(self, e: ReactionEvent) -> None:
        for h in self._reaction_handlers:
            try:
                if not h.filt(e):
                    continue
                await h.fn(e)
                if h.stop:
                    break
            except StopPropagation:
                break
            except Exception as ex:  # noqa: BLE001
                logger.exception("Handler crashed", exc_info=ex)

    def on_deleted_messages(
        self,
        filt: Callable[[DeletedMessagesEvent], bool] | None = None,
        *,
        stop: bool = False,
    ) -> Callable[[DeletedHandler], DeletedHandler]:
        f = filt or (lambda _e: True)

        def _decorator(fn: DeletedHandler) -> DeletedHandler:
            self._deleted_handlers.append(_DeletedHandler(filt=f, fn=fn, stop=stop))
            return fn

        return _decorator

    async def dispatch_deleted_messages(self, e: DeletedMessagesEvent) -> None:
        for h in self._deleted_handlers:
            try:
                if not h.filt(e):
                    continue
                await h.fn(e)
                if h.stop:
                    break
            except StopPropagation:
                break
            except Exception as ex:  # noqa: BLE001
                logger.exception("Handler crashed", exc_info=ex)

