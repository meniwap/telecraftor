from __future__ import annotations

import asyncio

import pytest

from telecraft.bot.app import ReconnectPolicy, run_forever, run_userbot
from telecraft.bot.router import Router


def test_run_forever_no_reconnect_propagates() -> None:
    async def _run_once() -> None:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        asyncio.run(run_forever(_run_once, reconnect=ReconnectPolicy(enabled=False)))


def test_run_forever_retries_until_success() -> None:
    attempts = 0

    async def _run_once() -> None:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RuntimeError("boom")

    pol = ReconnectPolicy(
        enabled=True,
        initial_delay_seconds=0.0,
        max_delay_seconds=0.0,
        multiplier=1.0,
        jitter_ratio=0.0,
        max_attempts=5,
    )
    asyncio.run(run_forever(_run_once, reconnect=pol))
    assert attempts == 3


def test_run_forever_stop_event_exits() -> None:
    stop = asyncio.Event()
    stop.set()
    ran = False

    async def _run_once() -> None:
        nonlocal ran
        ran = True

    asyncio.run(run_forever(_run_once, stop_event=stop))
    assert ran is False


def test_run_userbot_closes_client_when_startup_hook_fails() -> None:
    class Client:
        def __init__(self) -> None:
            self.connect_calls = 0
            self.close_calls = 0

        async def connect(self) -> None:
            self.connect_calls += 1

        async def close(self) -> None:
            self.close_calls += 1

    client = Client()

    async def fail_startup(_client: object) -> None:
        raise RuntimeError("startup failed")

    with pytest.raises(RuntimeError, match="startup failed"):
        asyncio.run(
            run_userbot(
                client=client,
                router=Router(),
                reconnect=ReconnectPolicy(enabled=False),
                on_startup=fail_startup,
            )
        )

    assert client.connect_calls == 1
    assert client.close_calls == 1
