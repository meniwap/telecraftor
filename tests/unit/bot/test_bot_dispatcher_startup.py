from __future__ import annotations

import asyncio
from dataclasses import fields
from types import SimpleNamespace

import pytest

import telecraft.bot.dispatcher as dispatcher_module
from telecraft.bot.dispatcher import Dispatcher
from telecraft.bot.events import MessageEvent
from telecraft.bot.router import Router


class _Client:
    def __init__(self, *, bot: bool) -> None:
        self.bot = bot
        self.prime_calls = 0
        self.started = False

    async def get_me(self) -> object:
        return SimpleNamespace(bot=self.bot)

    async def prime_entities(self) -> None:
        self.prime_calls += 1

    async def start_updates(self) -> None:
        self.started = True

    async def recv_update(self) -> object:
        raise asyncio.CancelledError


def test_dispatcher__bot_startup_skips_unsupported_dialog_priming() -> None:
    async def _case() -> tuple[int, bool]:
        client = _Client(bot=True)
        dispatcher = Dispatcher(client=client, router=Router())
        try:
            await dispatcher.run()
        except asyncio.CancelledError:
            pass
        return client.prime_calls, client.started

    assert asyncio.run(_case()) == (0, True)


def test_dispatcher__user_startup_still_primes_entities() -> None:
    async def _case() -> tuple[int, bool]:
        client = _Client(bot=False)
        dispatcher = Dispatcher(client=client, router=Router())
        try:
            await dispatcher.run()
        except asyncio.CancelledError:
            pass
        return client.prime_calls, client.started

    assert asyncio.run(_case()) == (1, True)


def test_dispatcher__run_error_cancels_handlers_before_reconnect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _case() -> tuple[bool, list[str]]:
        handler_started = asyncio.Event()
        handler_cleaned_up = asyncio.Event()

        class _DisconnectClient:
            def __init__(self) -> None:
                self.recv_calls = 0

            async def get_me(self) -> object:
                return SimpleNamespace(bot=True)

            async def start_updates(self) -> None:
                return None

            async def recv_update(self) -> object:
                self.recv_calls += 1
                if self.recv_calls == 1:
                    return object()
                await handler_started.wait()
                raise ConnectionError("reconnect")

        client = _DisconnectClient()
        router = Router()

        @router.on_message()
        async def _stuck_handler(_event: MessageEvent) -> None:
            handler_started.set()
            try:
                await asyncio.Event().wait()
            finally:
                handler_cleaned_up.set()

        event = MessageEvent(
            client=client,
            raw=object(),
            peer_type="user",
            peer_id=1,
            msg_id=1,
            text="work",
        )
        monkeypatch.setattr(dispatcher_module, "parse_events", lambda **_kwargs: [event])

        with pytest.raises(ConnectionError, match="reconnect"):
            await Dispatcher(
                client=client,
                router=router,
                ignore_before_start=False,
                handler_shutdown_timeout_seconds=0.01,
            ).run()

        pending_dispatches = [
            task.get_name()
            for task in asyncio.all_tasks()
            if task is not asyncio.current_task()
            and not task.done()
            and task.get_name().startswith("telecraft-dispatch:")
        ]
        return handler_cleaned_up.is_set(), pending_dispatches

    assert asyncio.run(_case()) == (True, [])


def test_dispatcher__run_error_drains_already_accepted_messages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _case() -> list[int | None]:
        class _DisconnectClient:
            def __init__(self) -> None:
                self.recv_calls = 0

            async def get_me(self) -> object:
                return SimpleNamespace(bot=True)

            async def start_updates(self) -> None:
                return None

            async def recv_update(self) -> object:
                self.recv_calls += 1
                if self.recv_calls == 1:
                    return object()
                raise ConnectionError("reconnect")

        client = _DisconnectClient()
        router = Router()
        handled: list[int | None] = []

        @router.on_message()
        async def _finite_handler(event: MessageEvent) -> None:
            await asyncio.sleep(0.01)
            handled.append(event.msg_id)

        events = [
            MessageEvent(
                client=client,
                raw=object(),
                peer_type="user",
                peer_id=1,
                sender_id=1,
                msg_id=msg_id,
                text=f"work-{msg_id}",
            )
            for msg_id in (1, 2)
        ]
        monkeypatch.setattr(dispatcher_module, "parse_events", lambda **_kwargs: events)

        with pytest.raises(ConnectionError, match="reconnect"):
            await Dispatcher(client=client, router=router, ignore_before_start=False).run()
        return handled

    assert asyncio.run(_case()) == [1, 2]


def test_dispatcher__concurrency_limit_is_appended_for_positional_compatibility() -> None:
    dispatcher = Dispatcher(
        object(),
        Router(),
        True,
        True,
        10,
        "ignore",
        None,
        None,
        10,
        1.0,
        "sleep",
        ("updateNewMessage",),
        ("message",),
        True,
        True,
    )

    assert fields(Dispatcher)[-3].name == "max_concurrent_handlers"
    assert fields(Dispatcher)[-2].name == "max_pending_handlers"
    assert fields(Dispatcher)[-1].name == "handler_shutdown_timeout_seconds"
    assert dispatcher.trace_update_names == ("updateNewMessage",)
    assert dispatcher.trace_update_substrings == ("message",)
    assert dispatcher.trace_all_updates is True
    assert dispatcher.debug is True
    assert dispatcher.max_concurrent_handlers == 1
    assert dispatcher.max_pending_handlers == 4096
    assert dispatcher.handler_shutdown_timeout_seconds == 30.0
