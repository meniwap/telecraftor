from __future__ import annotations

import asyncio
from typing import Any

import pytest

from telecraft.client import Client
from tests.live._suite_shared import finalize_run, resolve_or_create_audit_peer, run_step

pytestmark = [pytest.mark.live, pytest.mark.live_optional]


async def _run_stories_readonly_suite(client: Client, ctx: Any, reporter: Any) -> None:
    await client.connect(timeout=ctx.cfg.timeout)
    results: list[Any] = []
    resource_ids: dict[str, object] = {}

    reporter.audit_peer = await resolve_or_create_audit_peer(client, ctx, reporter)
    await reporter.emit(
        client=client,
        status="START",
        step="run",
        details=f"run_id={ctx.run_id} lane=optional-stories-readonly",
    )

    async def step_stories_readonly_roundtrip() -> str:
        feed = await client.stories.feed.all(timeout=ctx.cfg.timeout)
        all_read = await client.stories.all_read_peers(timeout=ctx.cfg.timeout)
        resource_ids["stories_feed_type"] = type(feed).__name__
        resource_ids["stories_all_read_type"] = type(all_read).__name__
        return f"feed={type(feed).__name__} all_read={type(all_read).__name__}"

    await run_step(
        name="stories_readonly.roundtrip",
        fn=step_stories_readonly_roundtrip,
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


def test_stories_feed__all__roundtrip_live(
    client_v2: Client,
    live_context: Any,
    audit_reporter: Any,
) -> None:
    asyncio.run(_run_stories_readonly_suite(client_v2, live_context, audit_reporter))
