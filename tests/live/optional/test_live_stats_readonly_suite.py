from __future__ import annotations

import asyncio
import os
from typing import Any

import pytest

from telecraft.client import Client
from tests.live._suite_shared import finalize_run, resolve_or_create_audit_peer, run_step

pytestmark = [pytest.mark.live, pytest.mark.live_optional, pytest.mark.live_admin]


async def _run_stats_suite(client: Client, ctx: Any, reporter: Any) -> None:
    if not ctx.cfg.enable_admin:
        pytest.skip("Stats lane requires --live-admin")

    channel = os.environ.get("TELECRAFT_LIVE_STATS_CHANNEL", "").strip()
    if not channel:
        pytest.skip("Set TELECRAFT_LIVE_STATS_CHANNEL to enable stats live lane")

    await client.connect(timeout=ctx.cfg.timeout)
    results: list[Any] = []
    resource_ids: dict[str, object] = {"channel": channel}

    reporter.audit_peer = await resolve_or_create_audit_peer(client, ctx, reporter)
    await reporter.emit(
        client=client,
        status="START",
        step="run",
        details=f"run_id={ctx.run_id} lane=optional-stats channel={channel}",
    )

    async def step_stats_broadcast() -> str:
        out = await client.stats.channels.broadcast(channel, timeout=ctx.cfg.timeout)
        resource_ids["broadcast_type"] = type(out).__name__
        return f"broadcast={type(out).__name__}"

    await run_step(
        name="stats.channels.broadcast",
        fn=step_stats_broadcast,
        client=client,
        reporter=reporter,
        results=results,
    )

    await finalize_run(
        client=client,
        ctx=ctx,
        reporter=reporter,
        results=results,
        resource_ids=resource_ids,
    )


def test_stats_channels__broadcast__roundtrip_live(
    client_v2: Client,
    live_context: Any,
    audit_reporter: Any,
) -> None:
    asyncio.run(_run_stats_suite(client_v2, live_context, audit_reporter))
