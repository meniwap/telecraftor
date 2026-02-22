from __future__ import annotations

import asyncio

from telecraft.bot.events import InlineQueryEvent, PrecheckoutQueryEvent, ShippingQueryEvent
from telecraft.bot.router import Router


def test_router__inline_query_dispatch__returns_expected_shape() -> None:
    async def _case() -> list[int]:
        router = Router()
        seen: list[int] = []

        @router.on_inline_query()
        async def _h(e: InlineQueryEvent) -> None:
            seen.append(int(e.query_id))

        await router.dispatch_inline_query(
            InlineQueryEvent(
                client=object(),
                raw=object(),
                query_id=1,
                user_id=1,
                query="q",
                offset="",
                geo=None,
                peer_type=None,
            )
        )
        return seen

    assert asyncio.run(_case()) == [1]


def test_router__shipping_query_dispatch__returns_expected_shape() -> None:
    async def _case() -> list[int]:
        router = Router()
        seen: list[int] = []

        @router.on_shipping_query()
        async def _h(e: ShippingQueryEvent) -> None:
            seen.append(int(e.query_id))

        await router.dispatch_shipping_query(
            ShippingQueryEvent(
                client=object(),
                raw=object(),
                query_id=2,
                user_id=1,
                payload=b"x",
                shipping_address=object(),
            )
        )
        return seen

    assert asyncio.run(_case()) == [2]


def test_router__precheckout_query_dispatch__returns_expected_shape() -> None:
    async def _case() -> list[int]:
        router = Router()
        seen: list[int] = []

        @router.on_precheckout_query()
        async def _h(e: PrecheckoutQueryEvent) -> None:
            seen.append(int(e.query_id))

        await router.dispatch_precheckout_query(
            PrecheckoutQueryEvent(
                client=object(),
                raw=object(),
                query_id=3,
                user_id=1,
                payload=b"x",
                currency="USD",
                total_amount=100,
                info=None,
                shipping_option_id=None,
            )
        )
        return seen

    assert asyncio.run(_case()) == [3]
