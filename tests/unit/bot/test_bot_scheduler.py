from __future__ import annotations

import asyncio

from telecraft.bot.scheduler import Scheduler


def test_scheduler__call_later__returns_expected_shape() -> None:
    async def _case() -> bool:
        scheduler = Scheduler()
        ran = False

        def _job() -> None:
            nonlocal ran
            ran = True

        scheduler.call_later(0.01, _job, name="once")
        await asyncio.sleep(0.05)
        await scheduler.stop()
        return ran

    assert asyncio.run(_case()) is True


def test_scheduler__every__returns_expected_shape() -> None:
    async def _case() -> int:
        scheduler = Scheduler()
        counter = 0

        async def _job() -> None:
            nonlocal counter
            counter += 1

        job = scheduler.every(0.01, _job, name="tick", run_immediately=True)
        await asyncio.sleep(0.05)
        job.cancel()
        await scheduler.stop()
        return counter

    assert asyncio.run(_case()) >= 2
