from __future__ import annotations

import asyncio

from telecraft.bot.events import CallbackQueryEvent
from telecraft.bot.router import Router


def _event() -> CallbackQueryEvent:
    return CallbackQueryEvent(
        client=object(),
        raw=object(),
        query_id=1,
        user_id=2,
        peer_type="chat",
        peer_id=3,
        msg_id=4,
        inline_msg_id=None,
        data=b"ok",
        game_short_name=None,
        chat_instance=5,
    )


def test_router__callback_query_middleware_chain__returns_expected_shape() -> None:
    async def _case() -> list[str]:
        router = Router()
        order: list[str] = []

        async def mw(evt: CallbackQueryEvent, nxt):
            _ = evt
            order.append("before")
            await nxt()
            order.append("after")

        router.use_callback_query(mw)

        @router.on_callback_query()
        async def _handler(e: CallbackQueryEvent) -> None:
            _ = e
            order.append("handler")

        await router.dispatch_callback_query(_event())
        return order

    assert asyncio.run(_case()) == ["before", "handler", "after"]


def test_router__callback_query_stop__returns_expected_shape() -> None:
    async def _case() -> list[str]:
        router = Router()
        calls: list[str] = []

        @router.on_callback_query(stop=True)
        async def _first(e: CallbackQueryEvent) -> None:
            _ = e
            calls.append("first")

        @router.on_callback_query()
        async def _second(e: CallbackQueryEvent) -> None:
            _ = e
            calls.append("second")

        await router.dispatch_callback_query(_event())
        return calls

    assert asyncio.run(_case()) == ["first"]
