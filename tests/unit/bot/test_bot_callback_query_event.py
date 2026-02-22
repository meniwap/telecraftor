from __future__ import annotations

import asyncio
from dataclasses import dataclass

from telecraft.bot.events import CallbackQueryEvent, parse_events
from telecraft.tl.generated.functions import MessagesSetBotCallbackAnswer


@dataclass
class _PeerChat:
    TL_NAME = "peerChat"

    chat_id: int


@dataclass
class _UpdateBotCallbackQuery:
    TL_NAME = "updateBotCallbackQuery"

    query_id: int
    user_id: int
    peer: object
    msg_id: int
    chat_instance: int
    data: bytes
    game_short_name: object | None = None


@dataclass
class _UpdateInlineBotCallbackQuery:
    TL_NAME = "updateInlineBotCallbackQuery"

    query_id: int
    user_id: int
    msg_id: object
    chat_instance: int
    data: bytes
    game_short_name: object | None = None


class _Client:
    def __init__(self) -> None:
        self.calls: list[tuple[object, float]] = []

    async def invoke_api(self, req: object, *, timeout: float) -> object:
        self.calls.append((req, timeout))
        return {"ok": True}


def test_callback_query_event__from_update_bot_callback_query__returns_expected_shape() -> None:
    upd = _UpdateBotCallbackQuery(
        query_id=101,
        user_id=7,
        peer=_PeerChat(chat_id=42),
        msg_id=88,
        chat_instance=999,
        data=b"yes",
    )
    e = CallbackQueryEvent.from_update(client=object(), update=upd)
    assert e is not None
    assert e.query_id == 101
    assert e.user_id == 7
    assert e.peer_type == "chat"
    assert e.peer_id == 42
    assert e.msg_id == 88
    assert e.inline_msg_id is None
    assert e.data == b"yes"
    assert e.data_text == "yes"


def test_callback_query_event__from_update_inline_callback_query__returns_expected_shape() -> None:
    inline_id = object()
    upd = _UpdateInlineBotCallbackQuery(
        query_id=202,
        user_id=9,
        msg_id=inline_id,
        chat_instance=111,
        data=b"no",
    )
    e = CallbackQueryEvent.from_update(client=object(), update=upd)
    assert e is not None
    assert e.query_id == 202
    assert e.user_id == 9
    assert e.peer_type is None
    assert e.peer_id is None
    assert e.msg_id is None
    assert e.inline_msg_id is inline_id
    assert e.data == b"no"


def test_callback_query_event__answer__invokes_set_bot_callback_answer() -> None:
    async def _case() -> tuple[object | None, _Client]:
        c = _Client()
        e = CallbackQueryEvent(
            client=c,
            raw=object(),
            query_id=303,
            user_id=1,
            peer_type="chat",
            peer_id=42,
            msg_id=7,
            inline_msg_id=None,
            data=b"data",
            game_short_name=None,
            chat_instance=555,
        )
        out = await e.answer(
            message="ok",
            alert=True,
            url="https://example.com",
            cache_time=5,
            timeout=9.0,
        )
        return out, c

    out, c = asyncio.run(_case())
    assert out == {"ok": True}
    assert len(c.calls) == 1
    req, timeout = c.calls[0]
    assert isinstance(req, MessagesSetBotCallbackAnswer)
    assert req.query_id == 303
    assert req.message == "ok"
    assert req.url == "https://example.com"
    assert req.cache_time == 5
    assert req.alert is True
    assert req.flags == 7
    assert timeout == 9.0


def test_callback_query_event__answer__respects_allow_reply_false() -> None:
    async def _case() -> _Client:
        c = _Client()
        e = CallbackQueryEvent(
            client=c,
            raw=object(),
            query_id=404,
            user_id=1,
            peer_type="chat",
            peer_id=42,
            msg_id=7,
            inline_msg_id=None,
            data=b"data",
            game_short_name=None,
            chat_instance=555,
            allow_reply=False,
        )
        out = await e.answer(message="nope")
        assert out is None
        return c

    c = asyncio.run(_case())
    assert c.calls == []


def test_parse_events__includes_callback_query_event() -> None:
    upd = _UpdateBotCallbackQuery(
        query_id=909,
        user_id=1,
        peer=_PeerChat(chat_id=11),
        msg_id=22,
        chat_instance=333,
        data=b"a",
    )
    evts = parse_events(client=object(), update=upd)
    assert len(evts) == 1
    assert isinstance(evts[0], CallbackQueryEvent)
