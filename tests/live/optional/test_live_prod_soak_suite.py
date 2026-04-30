from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

from telecraft.client import Client
from tests.live._suite_shared import finalize_run, resolve_or_create_audit_peer, run_step

pytestmark = [pytest.mark.live, pytest.mark.live_optional, pytest.mark.live_soak]


async def _run_prod_soak_suite(client: Client, ctx: Any, reporter: Any) -> None:
    if not ctx.cfg.enable_soak:
        pytest.skip("Prod soak lane requires --live-soak")

    await client.connect(timeout=ctx.cfg.timeout)
    results: list[Any] = []
    resource_ids: dict[str, object] = {}

    reporter.audit_peer = await resolve_or_create_audit_peer(client, ctx, reporter)
    await reporter.emit(
        client=client,
        status="START",
        step="run",
        details=f"run_id={ctx.run_id} lane=prod-soak duration={ctx.cfg.soak_duration}",
    )

    duration = max(10.0, float(ctx.cfg.soak_duration))
    interval = min(30.0, max(5.0, duration / 10.0))
    started = time.monotonic()
    iteration = 0

    while time.monotonic() - started < duration:
        iteration += 1

        async def step_soak_iteration(iteration: int = iteration) -> str:
            me = await client.profile.me(timeout=ctx.cfg.timeout)
            dialogs = await client.dialogs.list(limit=1, timeout=ctx.cfg.timeout)
            cfg = await client.help.config(timeout=ctx.cfg.timeout)
            resource_ids[f"iteration_{iteration}_me_type"] = type(me).__name__
            resource_ids[f"iteration_{iteration}_dialogs_type"] = type(dialogs).__name__
            resource_ids[f"iteration_{iteration}_config_type"] = type(cfg).__name__
            return (
                f"iteration={iteration} me={type(me).__name__} "
                f"dialogs={type(dialogs).__name__} config={type(cfg).__name__}"
            )

        await run_step(
            name=f"soak.iteration.{iteration}",
            fn=step_soak_iteration,
            client=client,
            reporter=reporter,
            results=results,
        )

        elapsed = time.monotonic() - started
        if elapsed >= duration:
            break
        await asyncio.sleep(min(interval, duration - elapsed))

    resource_ids["iterations"] = iteration
    resource_ids["duration_seconds"] = round(time.monotonic() - started, 3)

    await finalize_run(
        client=client,
        ctx=ctx,
        reporter=reporter,
        results=results,
        resource_ids=resource_ids,
    )


def test_prod_soak__read_health_loop__live_optional(
    client_v2: Client,
    live_context: Any,
    audit_reporter: Any,
) -> None:
    asyncio.run(_run_prod_soak_suite(client_v2, live_context, audit_reporter))
