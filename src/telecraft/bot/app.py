from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from telecraft.bot.dispatcher import Dispatcher
from telecraft.bot.router import Router

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ReconnectPolicy:
    """
    Simple reconnect/backoff policy for long-running userbots.
    """

    enabled: bool = True
    initial_delay_seconds: float = 1.0
    max_delay_seconds: float = 30.0
    multiplier: float = 2.0
    jitter_ratio: float = 0.2
    max_attempts: int | None = None

    def jittered(self, delay: float) -> float:
        j = max(0.0, min(float(self.jitter_ratio), 1.0))
        if j <= 0:
            return float(delay)
        lo = float(delay) * (1.0 - j)
        hi = float(delay) * (1.0 + j)
        return random.uniform(lo, hi)


async def run_forever(
    run_once: Callable[[], Awaitable[None]],
    *,
    stop_event: asyncio.Event | None = None,
    reconnect: ReconnectPolicy | None = None,
    on_error: Callable[[BaseException, int], Awaitable[None]] | None = None,
) -> None:
    """
    Run `run_once()` until it completes, or (if reconnect enabled) keep retrying on error.

    - stop_event: if set, exit between attempts
    - on_error: async hook called as on_error(exc, attempt_no)
    """
    pol = reconnect or ReconnectPolicy()
    attempt = 0
    delay = float(pol.initial_delay_seconds)

    while True:
        if stop_event is not None and stop_event.is_set():
            return
        try:
            await run_once()
            return
        except asyncio.CancelledError:
            raise
        except Exception as ex:  # noqa: BLE001
            attempt += 1
            if on_error is not None:
                try:
                    await on_error(ex, int(attempt))
                except Exception:  # noqa: BLE001
                    logger.exception("on_error hook failed; ignoring")
            logger.info("App run failed (attempt=%s): %s", attempt, type(ex).__name__, exc_info=ex)

            if not pol.enabled:
                raise
            if pol.max_attempts is not None and attempt >= int(pol.max_attempts):
                raise

            sleep_for = pol.jittered(delay)
            await asyncio.sleep(float(max(0.0, sleep_for)))
            delay = min(float(pol.max_delay_seconds), float(delay) * float(pol.multiplier))


async def run_userbot(
    *,
    client: Any,
    router: Router,
    make_dispatcher: Callable[[Any, Router], Dispatcher] | None = None,
    reconnect: ReconnectPolicy | None = None,
    stop_event: asyncio.Event | None = None,
    on_startup: Callable[[Any], Awaitable[None]] | None = None,
    on_shutdown: Callable[[Any], Awaitable[None]] | None = None,
) -> None:
    """
    Stable userbot runner:
    - connect
    - run Dispatcher loop
    - on error: close + reconnect with backoff
    """

    def _make_disp(c: Any, r: Router) -> Dispatcher:
        if make_dispatcher is not None:
            return make_dispatcher(c, r)
        return Dispatcher(client=c, router=r)

    async def _run_once() -> None:
        await client.connect()
        if on_startup is not None:
            await on_startup(client)
        disp = _make_disp(client, router)
        try:
            await disp.run()
        finally:
            if on_shutdown is not None:
                try:
                    await on_shutdown(client)
                except Exception as ex:  # noqa: BLE001
                    logger.info("on_shutdown hook failed; ignoring", exc_info=ex)
            try:
                await client.close()
            except Exception as ex:  # noqa: BLE001
                logger.info("client.close failed; ignoring", exc_info=ex)

    await run_forever(_run_once, stop_event=stop_event, reconnect=reconnect)
