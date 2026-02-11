from __future__ import annotations

import asyncio
from typing import Any

import pytest

from telecraft.client import Client
from tests.live._suite_shared import finalize_run, resolve_or_create_audit_peer, run_step

pytestmark = [pytest.mark.live, pytest.mark.live_optional]


async def _run_gifts_readonly_suite(client: Client, ctx: Any, reporter: Any) -> None:
    await client.connect(timeout=ctx.cfg.timeout)
    results: list[Any] = []
    resource_ids: dict[str, object] = {}

    reporter.audit_peer = await resolve_or_create_audit_peer(client, ctx, reporter)
    await reporter.emit(
        client=client,
        status="START",
        step="run",
        details=f"run_id={ctx.run_id} lane=optional-gifts-readonly",
    )

    async def step_gifts_roundtrip() -> str:
        catalog = await client.gifts.catalog(timeout=ctx.cfg.timeout)
        saved = await client.gifts.saved.list(peer="self", limit=10, timeout=ctx.cfg.timeout)
        resource_ids["gifts_catalog_type"] = type(catalog).__name__
        resource_ids["gifts_saved_type"] = type(saved).__name__
        return f"catalog={type(catalog).__name__} saved={type(saved).__name__}"

    await run_step(
        name="gifts.roundtrip",
        fn=step_gifts_roundtrip,
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


def test_gifts__catalog__roundtrip_live(
    client_v2: Client,
    live_context: Any,
    audit_reporter: Any,
) -> None:
    asyncio.run(_run_gifts_readonly_suite(client_v2, live_context, audit_reporter))
