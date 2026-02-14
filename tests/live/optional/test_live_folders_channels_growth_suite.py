from __future__ import annotations

import asyncio
from typing import Any

import pytest

from telecraft.client import Client
from tests.live._suite_shared import finalize_run, resolve_or_create_audit_peer, run_step

pytestmark = [pytest.mark.live, pytest.mark.live_optional]


async def _run_folders_channels_growth_suite(client: Client, ctx: Any, reporter: Any) -> None:
    await client.connect(timeout=ctx.cfg.timeout)
    results: list[Any] = []
    resource_ids: dict[str, object] = {}

    reporter.audit_peer = await resolve_or_create_audit_peer(client, ctx, reporter)

    async def step_discovery_and_search() -> str:
        groups = await client.discovery.channels.groups_for_discussion(timeout=ctx.cfg.timeout)
        posts = await client.channels.search_posts(limit=3, timeout=ctx.cfg.timeout)
        resource_ids["groups_type"] = type(groups).__name__
        resource_ids["posts_type"] = type(posts).__name__
        return f"groups={type(groups).__name__} posts={type(posts).__name__}"

    await run_step(
        name="folders_channels_growth.roundtrip",
        fn=step_discovery_and_search,
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


def test_folders_channels_growth__roundtrip__live_optional(
    client_v2: Client,
    live_context: Any,
    audit_reporter: Any,
) -> None:
    asyncio.run(_run_folders_channels_growth_suite(client_v2, live_context, audit_reporter))
