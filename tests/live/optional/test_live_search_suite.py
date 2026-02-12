from __future__ import annotations

import asyncio
from typing import Any

import pytest

from telecraft.client import Client
from tests.live._suite_shared import finalize_run, resolve_or_create_audit_peer, run_step

pytestmark = [pytest.mark.live, pytest.mark.live_optional]


async def _run_search_suite(client: Client, ctx: Any, reporter: Any) -> None:
    await client.connect(timeout=ctx.cfg.timeout)
    results: list[Any] = []
    resource_ids: dict[str, object] = {}

    reporter.audit_peer = await resolve_or_create_audit_peer(client, ctx, reporter)
    await reporter.emit(
        client=client,
        status="START",
        step="run",
        details=f"run_id={ctx.run_id} lane=optional-search",
    )

    async def step_search_roundtrip() -> str:
        global_res = await client.search.global_messages(limit=5, timeout=ctx.cfg.timeout)
        counters = await client.search.counters(
            str(reporter.audit_peer),
            timeout=ctx.cfg.timeout,
        )
        resource_ids["global_type"] = type(global_res).__name__
        resource_ids["counters_type"] = type(counters).__name__
        return f"global={type(global_res).__name__} counters={type(counters).__name__}"

    await run_step(
        name="search.roundtrip",
        fn=step_search_roundtrip,
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


def test_search__global_messages__roundtrip_live(
    client_v2: Client,
    live_context: Any,
    audit_reporter: Any,
) -> None:
    asyncio.run(_run_search_suite(client_v2, live_context, audit_reporter))
