from __future__ import annotations

import asyncio
from typing import Any

import pytest

from telecraft.client import Client
from tests.live._suite_shared import finalize_run, resolve_or_create_audit_peer, run_step

pytestmark = [
    pytest.mark.live,
    pytest.mark.live_optional,
    pytest.mark.live_sponsored,
    pytest.mark.live_admin,
]


async def _run_channels_sponsored_suite(client: Client, ctx: Any, reporter: Any) -> None:
    await client.connect(timeout=ctx.cfg.timeout)
    results: list[Any] = []
    resource_ids: dict[str, object] = {}

    reporter.audit_peer = await resolve_or_create_audit_peer(client, ctx, reporter)

    async def step_search_flood_probe() -> str:
        out = await client.channels.search_posts.check_flood("telegram", timeout=ctx.cfg.timeout)
        resource_ids["search_flood_type"] = type(out).__name__
        return f"search_flood={type(out).__name__}"

    await run_step(
        name="channels_sponsored.search_posts_flood",
        fn=step_search_flood_probe,
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


def test_channels_sponsored__check_flood__live_optional(
    client_v2: Client,
    live_context: Any,
    audit_reporter: Any,
) -> None:
    asyncio.run(_run_channels_sponsored_suite(client_v2, live_context, audit_reporter))
