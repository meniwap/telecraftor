from __future__ import annotations

import asyncio
from collections import deque

from telecraft.bot.dispatcher import Dispatcher
from telecraft.bot.events import InlineQueryEvent, PrecheckoutQueryEvent, ShippingQueryEvent
from telecraft.bot.router import Router


def test_dispatcher__inline_query_dedupe__returns_expected_shape() -> None:
    seen: list[int] = []
    router = Router()

    @router.on_inline_query()
    async def _h(e: InlineQueryEvent) -> None:
        seen.append(int(e.query_id))

    disp = Dispatcher(client=object(), router=router, ignore_before_start=False)

    async def _run() -> None:
        seen_other: set[tuple[str, str, int, int]] = set()
        seen_other_order: deque[tuple[str, str, int, int]] = deque(maxlen=4096)
        e = InlineQueryEvent(
            client=object(),
            raw=object(),
            query_id=55,
            user_id=1,
            query="cat",
            offset="",
            geo=None,
            peer_type=None,
        )
        await disp._handle_inline_query(  # noqa: SLF001
            e,
            started_at=0,
            now_ts=999999,
            seen_other=seen_other,
            seen_other_order=seen_other_order,
            global_bucket=None,
            peer_rate_per_sec=None,
            peer_buckets={},
        )
        await disp._handle_inline_query(  # noqa: SLF001
            e,
            started_at=0,
            now_ts=999999,
            seen_other=seen_other,
            seen_other_order=seen_other_order,
            global_bucket=None,
            peer_rate_per_sec=None,
            peer_buckets={},
        )

    asyncio.run(_run())
    assert seen == [55]


def test_dispatcher__shipping_query_process_no_reply__returns_expected_shape() -> None:
    seen: list[tuple[bool, bool]] = []
    router = Router()

    @router.on_shipping_query()
    async def _h(e: ShippingQueryEvent) -> None:
        seen.append((bool(e.is_backlog), bool(e.allow_reply)))

    disp = Dispatcher(
        client=object(),
        router=router,
        ignore_before_start=True,
        backlog_policy="process_no_reply",
        backlog_grace_seconds=60,
    )

    async def _run() -> None:
        seen_other: set[tuple[str, str, int, int]] = set()
        seen_other_order: deque[tuple[str, str, int, int]] = deque(maxlen=4096)
        e = ShippingQueryEvent(
            client=object(),
            raw=object(),
            query_id=66,
            user_id=2,
            payload=b"x",
            shipping_address=object(),
        )
        await disp._handle_shipping_query(  # noqa: SLF001
            e,
            started_at=100,
            now_ts=100,
            seen_other=seen_other,
            seen_other_order=seen_other_order,
            global_bucket=None,
            peer_rate_per_sec=None,
            peer_buckets={},
        )

    asyncio.run(_run())
    assert seen == [(True, False)]


def test_dispatcher__precheckout_query_dedupe__returns_expected_shape() -> None:
    seen: list[int] = []
    router = Router()

    @router.on_precheckout_query()
    async def _h(e: PrecheckoutQueryEvent) -> None:
        seen.append(int(e.query_id))

    disp = Dispatcher(client=object(), router=router, ignore_before_start=False)

    async def _run() -> None:
        seen_other: set[tuple[str, str, int, int]] = set()
        seen_other_order: deque[tuple[str, str, int, int]] = deque(maxlen=4096)
        e = PrecheckoutQueryEvent(
            client=object(),
            raw=object(),
            query_id=77,
            user_id=3,
            payload=b"x",
            currency="USD",
            total_amount=100,
            info=None,
            shipping_option_id=None,
        )
        await disp._handle_precheckout_query(  # noqa: SLF001
            e,
            started_at=0,
            now_ts=999999,
            seen_other=seen_other,
            seen_other_order=seen_other_order,
            global_bucket=None,
            peer_rate_per_sec=None,
            peer_buckets={},
        )
        await disp._handle_precheckout_query(  # noqa: SLF001
            e,
            started_at=0,
            now_ts=999999,
            seen_other=seen_other,
            seen_other_order=seen_other_order,
            global_bucket=None,
            peer_rate_per_sec=None,
            peer_buckets={},
        )

    asyncio.run(_run())
    assert seen == [77]
