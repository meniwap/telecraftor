from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from telecraft.bot.events import (
    ChatActionEvent,
    DeletedMessagesEvent,
    MemberUpdateEvent,
    MessageEvent,
    ReactionEvent,
)
from telecraft.bot.exceptions import StopPropagation
from telecraft.bot.filters import ActionFilter, Filter, MemberFilter, all_

Handler = Callable[[MessageEvent], Awaitable[None]]
ActionHandler = Callable[[ChatActionEvent], Awaitable[None]]
MemberHandler = Callable[[MemberUpdateEvent], Awaitable[None]]
ReactionHandler = Callable[[ReactionEvent], Awaitable[None]]
DeletedHandler = Callable[[DeletedMessagesEvent], Awaitable[None]]

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class _MessageHandler:
    filt: Filter
    fn: Handler
    stop: bool = False


@dataclass(slots=True)
class _ActionHandler:
    filt: ActionFilter
    fn: ActionHandler
    stop: bool = False


@dataclass(slots=True)
class _MemberHandler:
    filt: MemberFilter
    fn: MemberHandler
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
        self._action_handlers: list[_ActionHandler] = []
        self._member_handlers: list[_MemberHandler] = []
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

    def on_action(
        self, filt: ActionFilter | None = None, *, stop: bool = False
    ) -> Callable[[ActionHandler], ActionHandler]:
        f = filt or (lambda _e: True)

        def _decorator(fn: ActionHandler) -> ActionHandler:
            self._action_handlers.append(_ActionHandler(filt=f, fn=fn, stop=stop))
            return fn

        return _decorator

    async def dispatch_action(self, e: ChatActionEvent) -> None:
        for h in self._action_handlers:
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

    def on_member_update(
        self, filt: MemberFilter | None = None, *, stop: bool = False
    ) -> Callable[[MemberHandler], MemberHandler]:
        f = filt or (lambda _e: True)

        def _decorator(fn: MemberHandler) -> MemberHandler:
            self._member_handlers.append(_MemberHandler(filt=f, fn=fn, stop=stop))
            return fn

        return _decorator

    async def dispatch_member_update(self, e: MemberUpdateEvent) -> None:
        for h in self._member_handlers:
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
