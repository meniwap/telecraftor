from __future__ import annotations

import asyncio

from telecraft.bot.events import MessageEvent
from telecraft.bot.router import Router


class _Client:
    def __init__(self) -> None:
        self.sent: list[tuple[object, str]] = []

    async def send_message(
        self,
        peer: object,
        text: str,
        *,
        reply_to_msg_id: int | None = None,
        reply_markup: object | None = None,
    ) -> object:
        _ = (reply_to_msg_id, reply_markup)
        self.sent.append((peer, text))
        return {"ok": True}


def test_router__message_middleware_chain__returns_expected_shape() -> None:
    async def _case() -> list[str]:
        router = Router()
        order: list[str] = []

        async def mw(evt: MessageEvent, nxt):
            _ = evt
            order.append("before")
            await nxt()
            order.append("after")

        router.use_message(mw)

        @router.on_message()
        async def _handler(e: MessageEvent) -> None:
            _ = e
            order.append("handler")

        evt = MessageEvent(client=object(), raw=object(), peer_type="user", peer_id=1, msg_id=1)
        await router.dispatch_message(evt)
        return order

    assert asyncio.run(_case()) == ["before", "handler", "after"]


def test_router__wait_for_message__returns_expected_shape() -> None:
    async def _case() -> int | None:
        router = Router()
        wait_task = asyncio.create_task(router.wait_for_message(timeout=1.0))
        await asyncio.sleep(0)
        evt = MessageEvent(client=object(), raw=object(), peer_type="user", peer_id=7, msg_id=42)
        await router.dispatch_message(evt)
        out = await wait_task
        return out.msg_id

    assert asyncio.run(_case()) == 42


def test_router__ask__returns_expected_shape() -> None:
    async def _case() -> tuple[int | None, int]:
        client = _Client()
        router = Router()
        trigger = MessageEvent(client=client, raw=object(), peer_type="chat", peer_id=10, msg_id=1)
        ask_task = asyncio.create_task(router.ask(trigger, "question?", timeout=1.0))
        await asyncio.sleep(0)
        answer = MessageEvent(
            client=client,
            raw=object(),
            peer_type="chat",
            peer_id=10,
            msg_id=2,
            text="answer",
        )
        await router.dispatch_message(answer)
        out = await ask_task
        return out.msg_id, len(client.sent)

    assert asyncio.run(_case()) == (2, 1)
