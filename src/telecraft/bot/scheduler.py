from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

JobCallable = Callable[[], Awaitable[Any] | Any]


@dataclass(slots=True)
class ScheduledJob:
    name: str
    task: asyncio.Task[Any]
    interval_seconds: float | None = None

    def cancel(self) -> None:
        if not self.task.done():
            self.task.cancel()


class Scheduler:
    def __init__(self) -> None:
        self._jobs: dict[str, ScheduledJob] = {}
        self._counter = 0

    @property
    def jobs(self) -> dict[str, ScheduledJob]:
        return dict(self._jobs)

    async def _run_callable(self, fn: JobCallable) -> None:
        out = fn()
        if asyncio.iscoroutine(out) or isinstance(out, Awaitable):
            await out

    def _new_name(self, prefix: str) -> str:
        self._counter += 1
        return f"{prefix}-{self._counter}"

    def call_later(
        self,
        delay_seconds: float,
        fn: JobCallable,
        *,
        name: str | None = None,
    ) -> ScheduledJob:
        job_name = name or self._new_name("once")

        async def _runner() -> None:
            await asyncio.sleep(max(0.0, float(delay_seconds)))
            try:
                await self._run_callable(fn)
            finally:
                self._jobs.pop(job_name, None)

        task = asyncio.create_task(_runner(), name=f"telecraft-scheduler:{job_name}")
        job = ScheduledJob(name=job_name, task=task, interval_seconds=None)
        self._jobs[job_name] = job
        return job

    def every(
        self,
        interval_seconds: float,
        fn: JobCallable,
        *,
        name: str | None = None,
        run_immediately: bool = False,
    ) -> ScheduledJob:
        interval = max(0.001, float(interval_seconds))
        job_name = name or self._new_name("every")

        async def _runner() -> None:
            if run_immediately:
                try:
                    await self._run_callable(fn)
                except Exception as ex:  # noqa: BLE001
                    logger.exception("Scheduled job failed (job=%s)", job_name, exc_info=ex)
            while True:
                await asyncio.sleep(interval)
                try:
                    await self._run_callable(fn)
                except asyncio.CancelledError:
                    raise
                except Exception as ex:  # noqa: BLE001
                    logger.exception("Scheduled job failed (job=%s)", job_name, exc_info=ex)

        task = asyncio.create_task(_runner(), name=f"telecraft-scheduler:{job_name}")
        job = ScheduledJob(name=job_name, task=task, interval_seconds=interval)
        self._jobs[job_name] = job
        return job

    async def stop(self) -> None:
        jobs = list(self._jobs.values())
        self._jobs.clear()
        for job in jobs:
            job.cancel()
        if not jobs:
            return
        await asyncio.gather(*(job.task for job in jobs), return_exceptions=True)
