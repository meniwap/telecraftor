from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from telecraft.bot.conversations import ConversationManager
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
)
from telecraft.bot.exceptions import StopPropagation
from telecraft.bot.filters import ActionFilter, Filter, MemberFilter, all_

Handler = Callable[[MessageEvent], Awaitable[None]]
ActionHandler = Callable[[ChatActionEvent], Awaitable[None]]
MemberHandler = Callable[[MemberUpdateEvent], Awaitable[None]]
ReactionHandler = Callable[[ReactionEvent], Awaitable[None]]
DeletedHandler = Callable[[DeletedMessagesEvent], Awaitable[None]]
CallbackHandler = Callable[[CallbackQueryEvent], Awaitable[None]]
InlineQueryHandler = Callable[[InlineQueryEvent], Awaitable[None]]
ShippingQueryHandler = Callable[[ShippingQueryEvent], Awaitable[None]]
PrecheckoutQueryHandler = Callable[[PrecheckoutQueryEvent], Awaitable[None]]
MessageMiddleware = Callable[[MessageEvent, Callable[[], Awaitable[None]]], Awaitable[None]]
ActionMiddleware = Callable[[ChatActionEvent, Callable[[], Awaitable[None]]], Awaitable[None]]
MemberMiddleware = Callable[[MemberUpdateEvent, Callable[[], Awaitable[None]]], Awaitable[None]]
ReactionMiddleware = Callable[[ReactionEvent, Callable[[], Awaitable[None]]], Awaitable[None]]
DeletedMiddleware = Callable[[DeletedMessagesEvent, Callable[[], Awaitable[None]]], Awaitable[None]]
CallbackMiddleware = Callable[[CallbackQueryEvent, Callable[[], Awaitable[None]]], Awaitable[None]]
InlineQueryMiddleware = Callable[[InlineQueryEvent, Callable[[], Awaitable[None]]], Awaitable[None]]
ShippingQueryMiddleware = Callable[[ShippingQueryEvent, Callable[[], Awaitable[None]]], Awaitable[None]]
PrecheckoutQueryMiddleware = Callable[
    [PrecheckoutQueryEvent, Callable[[], Awaitable[None]]],
    Awaitable[None],
]

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


@dataclass(slots=True)
class _CallbackHandler:
    filt: Callable[[CallbackQueryEvent], bool]
    fn: CallbackHandler
    stop: bool = False


@dataclass(slots=True)
class _InlineQueryHandler:
    filt: Callable[[InlineQueryEvent], bool]
    fn: InlineQueryHandler
    stop: bool = False


@dataclass(slots=True)
class _ShippingQueryHandler:
    filt: Callable[[ShippingQueryEvent], bool]
    fn: ShippingQueryHandler
    stop: bool = False


@dataclass(slots=True)
class _PrecheckoutQueryHandler:
    filt: Callable[[PrecheckoutQueryEvent], bool]
    fn: PrecheckoutQueryHandler
    stop: bool = False


class Router:
    def __init__(self) -> None:
        self._message_handlers: list[_MessageHandler] = []
        self._action_handlers: list[_ActionHandler] = []
        self._member_handlers: list[_MemberHandler] = []
        self._reaction_handlers: list[_ReactionHandler] = []
        self._deleted_handlers: list[_DeletedHandler] = []
        self._callback_handlers: list[_CallbackHandler] = []
        self._inline_query_handlers: list[_InlineQueryHandler] = []
        self._shipping_query_handlers: list[_ShippingQueryHandler] = []
        self._precheckout_query_handlers: list[_PrecheckoutQueryHandler] = []
        self._message_middlewares: list[MessageMiddleware] = []
        self._action_middlewares: list[ActionMiddleware] = []
        self._member_middlewares: list[MemberMiddleware] = []
        self._reaction_middlewares: list[ReactionMiddleware] = []
        self._deleted_middlewares: list[DeletedMiddleware] = []
        self._callback_middlewares: list[CallbackMiddleware] = []
        self._inline_query_middlewares: list[InlineQueryMiddleware] = []
        self._shipping_query_middlewares: list[ShippingQueryMiddleware] = []
        self._precheckout_query_middlewares: list[PrecheckoutQueryMiddleware] = []
        self._conversations = ConversationManager()

    async def _run_middleware_chain(
        self,
        *,
        event: Any,
        middlewares: list[Callable[[Any, Callable[[], Awaitable[None]]], Awaitable[None]]],
        terminal: Callable[[], Awaitable[None]],
    ) -> None:
        idx = 0

        async def _next() -> None:
            nonlocal idx
            if idx >= len(middlewares):
                await terminal()
                return
            mw = middlewares[idx]
            idx += 1
            try:
                await mw(event, _next)
            except StopPropagation:
                raise
            except Exception as ex:  # noqa: BLE001
                logger.exception("Middleware crashed", exc_info=ex)
                await _next()

        await _next()

    def use_message(self, middleware: MessageMiddleware) -> None:
        self._message_middlewares.append(middleware)

    def use_action(self, middleware: ActionMiddleware) -> None:
        self._action_middlewares.append(middleware)

    def use_member_update(self, middleware: MemberMiddleware) -> None:
        self._member_middlewares.append(middleware)

    def use_reaction(self, middleware: ReactionMiddleware) -> None:
        self._reaction_middlewares.append(middleware)

    def use_deleted_messages(self, middleware: DeletedMiddleware) -> None:
        self._deleted_middlewares.append(middleware)

    def use_callback_query(self, middleware: CallbackMiddleware) -> None:
        self._callback_middlewares.append(middleware)

    def use_inline_query(self, middleware: InlineQueryMiddleware) -> None:
        self._inline_query_middlewares.append(middleware)

    def use_shipping_query(self, middleware: ShippingQueryMiddleware) -> None:
        self._shipping_query_middlewares.append(middleware)

    def use_precheckout_query(self, middleware: PrecheckoutQueryMiddleware) -> None:
        self._precheckout_query_middlewares.append(middleware)

    async def wait_for_message(
        self,
        *,
        filt: Filter | None = None,
        timeout: float | None = None,
        consume: bool = True,
    ) -> MessageEvent:
        return await self._conversations.wait_for_message(
            filt=filt,
            timeout=timeout,
            consume=consume,
        )

    async def ask(
        self,
        event: MessageEvent,
        text: str,
        *,
        filt: Filter | None = None,
        timeout: float | None = None,
        consume: bool = True,
        reply_kwargs: dict[str, Any] | None = None,
    ) -> MessageEvent:
        return await self._conversations.ask(
            event,
            text,
            filt=filt,
            timeout=timeout,
            consume=consume,
            reply_kwargs=reply_kwargs,
        )

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
        if self._conversations.feed_message(e):
            return

        async def _run_handlers() -> None:
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

        try:
            await self._run_middleware_chain(
                event=e,
                middlewares=list(self._message_middlewares),
                terminal=_run_handlers,
            )
        except StopPropagation:
            return

    def on_action(
        self, filt: ActionFilter | None = None, *, stop: bool = False
    ) -> Callable[[ActionHandler], ActionHandler]:
        f = filt or (lambda _e: True)

        def _decorator(fn: ActionHandler) -> ActionHandler:
            self._action_handlers.append(_ActionHandler(filt=f, fn=fn, stop=stop))
            return fn

        return _decorator

    async def dispatch_action(self, e: ChatActionEvent) -> None:
        async def _run_handlers() -> None:
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

        try:
            await self._run_middleware_chain(
                event=e,
                middlewares=list(self._action_middlewares),
                terminal=_run_handlers,
            )
        except StopPropagation:
            return

    def on_member_update(
        self, filt: MemberFilter | None = None, *, stop: bool = False
    ) -> Callable[[MemberHandler], MemberHandler]:
        f = filt or (lambda _e: True)

        def _decorator(fn: MemberHandler) -> MemberHandler:
            self._member_handlers.append(_MemberHandler(filt=f, fn=fn, stop=stop))
            return fn

        return _decorator

    async def dispatch_member_update(self, e: MemberUpdateEvent) -> None:
        async def _run_handlers() -> None:
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

        try:
            await self._run_middleware_chain(
                event=e,
                middlewares=list(self._member_middlewares),
                terminal=_run_handlers,
            )
        except StopPropagation:
            return

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
        async def _run_handlers() -> None:
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

        try:
            await self._run_middleware_chain(
                event=e,
                middlewares=list(self._reaction_middlewares),
                terminal=_run_handlers,
            )
        except StopPropagation:
            return

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
        async def _run_handlers() -> None:
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

        try:
            await self._run_middleware_chain(
                event=e,
                middlewares=list(self._deleted_middlewares),
                terminal=_run_handlers,
            )
        except StopPropagation:
            return

    def on_callback_query(
        self,
        filt: Callable[[CallbackQueryEvent], bool] | None = None,
        *,
        stop: bool = False,
    ) -> Callable[[CallbackHandler], CallbackHandler]:
        f = filt or (lambda _e: True)

        def _decorator(fn: CallbackHandler) -> CallbackHandler:
            self._callback_handlers.append(_CallbackHandler(filt=f, fn=fn, stop=stop))
            return fn

        return _decorator

    async def dispatch_callback_query(self, e: CallbackQueryEvent) -> None:
        async def _run_handlers() -> None:
            for h in self._callback_handlers:
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

        try:
            await self._run_middleware_chain(
                event=e,
                middlewares=list(self._callback_middlewares),
                terminal=_run_handlers,
            )
        except StopPropagation:
            return

    def on_inline_query(
        self,
        filt: Callable[[InlineQueryEvent], bool] | None = None,
        *,
        stop: bool = False,
    ) -> Callable[[InlineQueryHandler], InlineQueryHandler]:
        f = filt or (lambda _e: True)

        def _decorator(fn: InlineQueryHandler) -> InlineQueryHandler:
            self._inline_query_handlers.append(_InlineQueryHandler(filt=f, fn=fn, stop=stop))
            return fn

        return _decorator

    async def dispatch_inline_query(self, e: InlineQueryEvent) -> None:
        async def _run_handlers() -> None:
            for h in self._inline_query_handlers:
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

        try:
            await self._run_middleware_chain(
                event=e,
                middlewares=list(self._inline_query_middlewares),
                terminal=_run_handlers,
            )
        except StopPropagation:
            return

    def on_shipping_query(
        self,
        filt: Callable[[ShippingQueryEvent], bool] | None = None,
        *,
        stop: bool = False,
    ) -> Callable[[ShippingQueryHandler], ShippingQueryHandler]:
        f = filt or (lambda _e: True)

        def _decorator(fn: ShippingQueryHandler) -> ShippingQueryHandler:
            self._shipping_query_handlers.append(_ShippingQueryHandler(filt=f, fn=fn, stop=stop))
            return fn

        return _decorator

    async def dispatch_shipping_query(self, e: ShippingQueryEvent) -> None:
        async def _run_handlers() -> None:
            for h in self._shipping_query_handlers:
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

        try:
            await self._run_middleware_chain(
                event=e,
                middlewares=list(self._shipping_query_middlewares),
                terminal=_run_handlers,
            )
        except StopPropagation:
            return

    def on_precheckout_query(
        self,
        filt: Callable[[PrecheckoutQueryEvent], bool] | None = None,
        *,
        stop: bool = False,
    ) -> Callable[[PrecheckoutQueryHandler], PrecheckoutQueryHandler]:
        f = filt or (lambda _e: True)

        def _decorator(fn: PrecheckoutQueryHandler) -> PrecheckoutQueryHandler:
            self._precheckout_query_handlers.append(
                _PrecheckoutQueryHandler(filt=f, fn=fn, stop=stop)
            )
            return fn

        return _decorator

    async def dispatch_precheckout_query(self, e: PrecheckoutQueryEvent) -> None:
        async def _run_handlers() -> None:
            for h in self._precheckout_query_handlers:
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

        try:
            await self._run_middleware_chain(
                event=e,
                middlewares=list(self._precheckout_query_middlewares),
                terminal=_run_handlers,
            )
        except StopPropagation:
            return