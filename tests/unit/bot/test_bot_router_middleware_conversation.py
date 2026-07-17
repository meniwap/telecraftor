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


class _BlockingClient(_Client):
    def __init__(self) -> None:
        super().__init__()
        self.send_started = asyncio.Event()
        self.release_send = asyncio.Event()

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
        self.send_started.set()
        await self.release_send.wait()
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


def test_router__middleware_failure_after_next_does_not_run_handler_twice() -> None:
    async def _case() -> list[str]:
        router = Router()
        calls: list[str] = []

        async def failing_after_next(evt: MessageEvent, nxt) -> None:
            _ = evt
            calls.append("middleware")
            await nxt()
            raise RuntimeError("failed after downstream completed")

        router.use_message(failing_after_next)

        @router.on_message()
        async def _handler(e: MessageEvent) -> None:
            _ = e
            calls.append("handler")

        evt = MessageEvent(client=object(), raw=object(), peer_type="user", peer_id=1, msg_id=1)
        await router.dispatch_message(evt)
        return calls

    assert asyncio.run(_case()) == ["middleware", "handler"]


def test_router__middleware_failure_before_next_still_continues_chain() -> None:
    async def _case() -> list[str]:
        router = Router()
        calls: list[str] = []

        async def failing_before_next(evt: MessageEvent, nxt) -> None:
            _ = evt, nxt
            calls.append("middleware")
            raise RuntimeError("failed before downstream")

        router.use_message(failing_before_next)

        @router.on_message()
        async def _handler(e: MessageEvent) -> None:
            _ = e
            calls.append("handler")

        evt = MessageEvent(client=object(), raw=object(), peer_type="user", peer_id=1, msg_id=1)
        await router.dispatch_message(evt)
        return calls

    assert asyncio.run(_case()) == ["middleware", "handler"]


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


def test_router__ask__registers_waiter_before_sending_prompt() -> None:
    async def _case() -> tuple[bool, int | None]:
        client = _BlockingClient()
        router = Router()
        trigger = MessageEvent(
            client=client,
            raw=object(),
            peer_type="chat",
            peer_id=10,
            msg_id=1,
        )
        ask_task = asyncio.create_task(router.ask(trigger, "question?", timeout=1.0))
        await asyncio.wait_for(client.send_started.wait(), timeout=1.0)

        answer = MessageEvent(
            client=client,
            raw=object(),
            peer_type="chat",
            peer_id=10,
            msg_id=2,
            text="fast answer",
        )
        consumed_while_send_pending = router.feed_conversation_message(answer)
        client.release_send.set()
        out = await asyncio.wait_for(ask_task, timeout=1.0)
        return consumed_while_send_pending, out.msg_id

    assert asyncio.run(_case()) == (True, 2)


def test_router__ask__same_sender_is_opt_in() -> None:
    async def _case() -> int | None:
        client = _Client()
        router = Router()
        trigger = MessageEvent(
            client=client,
            raw=object(),
            peer_type="channel",
            peer_id=10,
            sender_id=7,
            msg_id=1,
        )
        ask_task = asyncio.create_task(router.ask(trigger, "question?", timeout=1.0))
        await asyncio.sleep(0)
        await router.dispatch_message(
            MessageEvent(
                client=client,
                raw=object(),
                peer_type="channel",
                peer_id=10,
                sender_id=8,
                msg_id=2,
                text="other sender is compatible by default",
            )
        )
        return (await ask_task).msg_id

    assert asyncio.run(_case()) == 2


def test_router__ask__ignores_other_sender_in_same_group() -> None:
    async def _case() -> tuple[bool, int | None]:
        client = _Client()
        router = Router()
        trigger = MessageEvent(
            client=client,
            raw=object(),
            peer_type="channel",
            peer_id=10,
            sender_id=7,
            msg_id=1,
        )
        ask_task = asyncio.create_task(
            router.ask(trigger, "question?", timeout=1.0, same_sender=True)
        )
        await asyncio.sleep(0)
        await router.dispatch_message(
            MessageEvent(
                client=client,
                raw=object(),
                peer_type="channel",
                peer_id=10,
                sender_id=8,
                msg_id=2,
                text="wrong sender",
            )
        )
        ignored_other_sender = not ask_task.done()
        await router.dispatch_message(
            MessageEvent(
                client=client,
                raw=object(),
                peer_type="channel",
                peer_id=10,
                sender_id=7,
                msg_id=3,
                text="right sender",
            )
        )
        out = await ask_task
        return ignored_other_sender, out.msg_id

    assert asyncio.run(_case()) == (True, 3)


def test_router__ask__unknown_sender_does_not_match_identified_sender() -> None:
    async def _case() -> tuple[bool, int | None]:
        client = _Client()
        router = Router()
        trigger = MessageEvent(
            client=client,
            raw=object(),
            peer_type="channel",
            peer_id=10,
            sender_id=None,
            msg_id=1,
        )
        ask_task = asyncio.create_task(
            router.ask(trigger, "question?", timeout=1.0, same_sender=True)
        )
        await asyncio.sleep(0)
        await router.dispatch_message(
            MessageEvent(
                client=client,
                raw=object(),
                peer_type="channel",
                peer_id=10,
                sender_id=8,
                msg_id=2,
                text="identified sender",
            )
        )
        ignored_identified_sender = not ask_task.done()
        await router.dispatch_message(
            MessageEvent(
                client=client,
                raw=object(),
                peer_type="channel",
                peer_id=10,
                sender_id=None,
                msg_id=3,
                text="same anonymous sender shape",
            )
        )
        return ignored_identified_sender, (await ask_task).msg_id

    assert asyncio.run(_case()) == (True, 3)
