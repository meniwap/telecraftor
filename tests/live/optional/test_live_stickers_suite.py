from __future__ import annotations

import asyncio
from typing import Any

import pytest

from telecraft.client import Client
from tests.live._suite_shared import finalize_run, resolve_or_create_audit_peer, run_step

pytestmark = [pytest.mark.live, pytest.mark.live_optional]


async def _run_stickers_suite(client: Client, ctx: Any, reporter: Any) -> None:
    await client.connect(timeout=ctx.cfg.timeout)
    results: list[Any] = []
    resource_ids: dict[str, object] = {}

    reporter.audit_peer = await resolve_or_create_audit_peer(client, ctx, reporter)
    await reporter.emit(
        client=client,
        status="START",
        step="run",
        details=f"run_id={ctx.run_id} lane=optional-stickers",
    )

    async def step_stickers_roundtrip() -> str:
        all_sets = await client.stickers.sets.all(timeout=ctx.cfg.timeout)
        featured = await client.stickers.sets.featured(timeout=ctx.cfg.timeout)
        resource_ids["all_type"] = type(all_sets).__name__
        resource_ids["featured_type"] = type(featured).__name__
        return f"all={type(all_sets).__name__} featured={type(featured).__name__}"

    await run_step(
        name="stickers.roundtrip",
        fn=step_stickers_roundtrip,
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


def test_stickers_sets__all__roundtrip_live(
    client_v2: Client,
    live_context: Any,
    audit_reporter: Any,
) -> None:
    asyncio.run(_run_stickers_suite(client_v2, live_context, audit_reporter))

