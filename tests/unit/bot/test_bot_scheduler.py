from __future__ import annotations

import asyncio

import pytest

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


def test_scheduler__cancel__removes_named_job() -> None:
    async def _case() -> tuple[bool, bool, bool]:
        scheduler = Scheduler()
        scheduler.every(60, lambda: None, name="long-job")
        existed_before = "long-job" in scheduler.jobs
        removed = await scheduler.cancel("long-job")
        removed_again = await scheduler.cancel("long-job")
        await scheduler.stop()
        return existed_before, removed, removed_again

    assert asyncio.run(_case()) == (True, True, False)


@pytest.mark.parametrize("run_immediately", [False, True])
def test_scheduler__repeating_job_can_cancel_itself(run_immediately: bool) -> None:
    async def _case() -> tuple[int, list[bool], bool, bool]:
        scheduler = Scheduler()
        calls = 0
        cancel_results: list[bool] = []

        async def _job() -> None:
            nonlocal calls
            calls += 1
            cancel_results.append(await scheduler.cancel("self-cancelling"))

        job = scheduler.every(
            0.001,
            _job,
            name="self-cancelling",
            run_immediately=run_immediately,
        )
        await asyncio.wait_for(job.task, timeout=1.0)
        empty = scheduler.jobs == {}
        removed_again = await scheduler.cancel("self-cancelling")
        await scheduler.stop()
        return calls, cancel_results, empty, removed_again

    assert asyncio.run(_case()) == (1, [True], True, False)


def test_scheduler__repeating_job_can_stop_scheduler() -> None:
    async def _case() -> tuple[int, bool]:
        scheduler = Scheduler()
        calls = 0

        async def _job() -> None:
            nonlocal calls
            calls += 1
            await scheduler.stop()

        job = scheduler.every(60, _job, name="self-stop", run_immediately=True)
        await asyncio.wait_for(job.task, timeout=1.0)
        return calls, scheduler.jobs == {}

    assert asyncio.run(_case()) == (1, True)
