from __future__ import annotations

import asyncio
from typing import Any

import pytest

from telecraft.client import Client
from tests.live._suite_shared import finalize_run, resolve_or_create_audit_peer, run_step

pytestmark = [
    pytest.mark.live,
    pytest.mark.live_optional,
    pytest.mark.live_business,
    pytest.mark.requires_business_account,
]


async def _run_business_suite(client: Client, ctx: Any, reporter: Any) -> None:
    await client.connect(timeout=ctx.cfg.timeout)
    results: list[Any] = []
    resource_ids: dict[str, object] = {}

    reporter.audit_peer = await resolve_or_create_audit_peer(client, ctx, reporter)
    await reporter.emit(
        client=client,
        status="START",
        step="run",
        details=f"run_id={ctx.run_id} lane=optional-business",
    )

    async def step_business_roundtrip() -> str:
        out = await client.business.links.list(timeout=ctx.cfg.timeout)
        resource_ids["business_links_type"] = type(out).__name__
        return f"business_links={type(out).__name__}"

    await run_step(
        name="business.roundtrip",
        fn=step_business_roundtrip,
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


def test_business_links__list__roundtrip_live(
    client_v2: Client,
    live_context: Any,
    audit_reporter: Any,
) -> None:
    asyncio.run(_run_business_suite(client_v2, live_context, audit_reporter))
