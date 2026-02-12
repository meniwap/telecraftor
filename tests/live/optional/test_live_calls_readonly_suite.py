from __future__ import annotations

import asyncio
import os
from typing import Any

import pytest

from telecraft.client import Client
from tests.live._suite_shared import finalize_run, resolve_or_create_audit_peer, run_step

pytestmark = [pytest.mark.live, pytest.mark.live_optional, pytest.mark.live_calls]


async def _run_calls_readonly_suite(client: Client, ctx: Any, reporter: Any) -> None:
    if not ctx.cfg.enable_calls:
        pytest.skip("Calls readonly lane requires --live-calls")

    calls_peer = os.environ.get("TELECRAFT_LIVE_CALLS_PEER", "").strip()
    if not calls_peer:
        pytest.skip("Set TELECRAFT_LIVE_CALLS_PEER to enable calls readonly lane")

    await client.connect(timeout=ctx.cfg.timeout)
    results: list[Any] = []
    resource_ids: dict[str, object] = {"calls_peer": calls_peer}

    reporter.audit_peer = await resolve_or_create_audit_peer(client, ctx, reporter)
    await reporter.emit(
        client=client,
        status="START",
        step="run",
        details=f"run_id={ctx.run_id} lane=optional-calls-readonly peer={calls_peer}",
    )

    async def step_calls_readonly() -> str:
        out = await client.calls.stream.rtmp_url(calls_peer, timeout=ctx.cfg.timeout)
        resource_ids["rtmp_type"] = type(out).__name__
        return f"rtmp={type(out).__name__}"

    await run_step(
        name="calls.stream.rtmp_url",
        fn=step_calls_readonly,
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


def test_calls_stream__rtmp_url__roundtrip_live(
    client_v2: Client,
    live_context: Any,
    audit_reporter: Any,
) -> None:
    asyncio.run(_run_calls_readonly_suite(client_v2, live_context, audit_reporter))
