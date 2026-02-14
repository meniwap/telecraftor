from __future__ import annotations

import asyncio
from typing import Any

import pytest

from telecraft.client import Client
from tests.live._suite_shared import finalize_run, resolve_or_create_audit_peer, run_step

pytestmark = [pytest.mark.live, pytest.mark.live_optional]


async def _run_stories_advanced_readonly_suite(client: Client, ctx: Any, reporter: Any) -> None:
    await client.connect(timeout=ctx.cfg.timeout)
    results: list[Any] = []
    resource_ids: dict[str, object] = {}

    reporter.audit_peer = await resolve_or_create_audit_peer(client, ctx, reporter)

    async def step_stories_advanced_readonly() -> str:
        chats = await client.stories.chats_to_send(timeout=ctx.cfg.timeout)
        read_peers = await client.stories.all_read_peers(timeout=ctx.cfg.timeout)
        resource_ids["chats_type"] = type(chats).__name__
        resource_ids["read_peers_type"] = type(read_peers).__name__
        return f"chats={type(chats).__name__} read_peers={type(read_peers).__name__}"

    await run_step(
        name="stories_advanced_readonly.roundtrip",
        fn=step_stories_advanced_readonly,
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


def test_stories_advanced_readonly__roundtrip__live_optional(
    client_v2: Client,
    live_context: Any,
    audit_reporter: Any,
) -> None:
    asyncio.run(_run_stories_advanced_readonly_suite(client_v2, live_context, audit_reporter))
