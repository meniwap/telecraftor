from __future__ import annotations

import asyncio
from dataclasses import dataclass

from telecraft.bot.events import (
    InlineQueryEvent,
    PrecheckoutQueryEvent,
    ShippingQueryEvent,
    parse_events,
)
from telecraft.tl.generated.functions import (
    MessagesSetBotPrecheckoutResults,
    MessagesSetBotShippingResults,
    MessagesSetInlineBotResults,
)


@dataclass
class _UpdateBotInlineQuery:
    TL_NAME = "updateBotInlineQuery"

    query_id: int
    user_id: int
    query: bytes
    offset: bytes
    geo: object | None = None
    peer_type: object | None = None


@dataclass
class _UpdateBotShippingQuery:
    TL_NAME = "updateBotShippingQuery"

    query_id: int
    user_id: int
    payload: bytes
    shipping_address: object


@dataclass
class _UpdateBotPrecheckoutQuery:
    TL_NAME = "updateBotPrecheckoutQuery"

    query_id: int
    user_id: int
    payload: bytes
    currency: bytes
    total_amount: int
    flags: int = 0
    info: object | None = None
    shipping_option_id: bytes | None = None


class _Client:
    def __init__(self) -> None:
        self.calls: list[tuple[object, float]] = []

    async def invoke_api(self, req: object, *, timeout: float) -> object:
        self.calls.append((req, timeout))
        return {"ok": True}


def test_inline_shipping_precheckout__parse_events__returns_expected_shape() -> None:
    inline = _UpdateBotInlineQuery(query_id=11, user_id=2, query=b"cat", offset=b"")
    shipping = _UpdateBotShippingQuery(
        query_id=22,
        user_id=3,
        payload=b"p",
        shipping_address=object(),
    )
    pre = _UpdateBotPrecheckoutQuery(
        query_id=33,
        user_id=4,
        payload=b"q",
        currency=b"USD",
        total_amount=1500,
    )

    ev_inline = parse_events(client=object(), update=inline)
    ev_shipping = parse_events(client=object(), update=shipping)
    ev_pre = parse_events(client=object(), update=pre)

    assert len(ev_inline) == 1 and isinstance(ev_inline[0], InlineQueryEvent)
    assert len(ev_shipping) == 1 and isinstance(ev_shipping[0], ShippingQueryEvent)
    assert len(ev_pre) == 1 and isinstance(ev_pre[0], PrecheckoutQueryEvent)


def test_inline_query_event__answer__invokes_set_inline_bot_results() -> None:
    async def _case() -> tuple[object, _Client]:
        c = _Client()
        e = InlineQueryEvent(
            client=c,
            raw=object(),
            query_id=101,
            user_id=7,
            query="q",
            offset="",
            geo=None,
            peer_type=None,
        )
        out = await e.answer(
            results=[],
            gallery=True,
            private=True,
            cache_time=5,
            next_offset="next",
            timeout=8.0,
        )
        return out, c

    out, c = asyncio.run(_case())
    assert out == {"ok": True}
    assert len(c.calls) == 1
    req, timeout = c.calls[0]
    assert isinstance(req, MessagesSetInlineBotResults)
    assert req.query_id == 101
    assert req.cache_time == 5
    assert req.next_offset == "next"
    assert req.flags == 7
    assert timeout == 8.0


def test_shipping_query_event__answer__invokes_set_bot_shipping_results() -> None:
    async def _case() -> tuple[object, _Client]:
        c = _Client()
        e = ShippingQueryEvent(
            client=c,
            raw=object(),
            query_id=202,
            user_id=8,
            payload=b"x",
            shipping_address=object(),
        )
        out = await e.answer(shipping_options=[], timeout=6.0)
        return out, c

    out, c = asyncio.run(_case())
    assert out == {"ok": True}
    req, timeout = c.calls[0]
    assert isinstance(req, MessagesSetBotShippingResults)
    assert req.query_id == 202
    assert req.flags == 2
    assert timeout == 6.0


def test_precheckout_query_event__answer__invokes_set_bot_precheckout_results() -> None:
    async def _case() -> tuple[object, object, _Client]:
        c = _Client()
        e = PrecheckoutQueryEvent(
            client=c,
            raw=object(),
            query_id=303,
            user_id=9,
            payload=b"x",
            currency="USD",
            total_amount=1000,
            info=None,
            shipping_option_id=None,
        )
        ok_out = await e.answer(success=True, timeout=7.0)
        err_out = await e.answer(error="denied", timeout=7.0)
        return ok_out, err_out, c

    ok_out, err_out, c = asyncio.run(_case())
    assert ok_out == {"ok": True}
    assert err_out == {"ok": True}
    req_ok, _t1 = c.calls[0]
    req_err, _t2 = c.calls[1]
    assert isinstance(req_ok, MessagesSetBotPrecheckoutResults)
    assert req_ok.query_id == 303
    assert req_ok.flags == 2
    assert isinstance(req_err, MessagesSetBotPrecheckoutResults)
    assert req_err.query_id == 303
    assert req_err.flags == 1
