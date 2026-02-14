from __future__ import annotations

import asyncio
from typing import Any

import pytest

from telecraft.client import Client
from tests.live._suite_shared import finalize_run, resolve_or_create_audit_peer, run_step

pytestmark = [pytest.mark.live, pytest.mark.live_optional]


async def _run_messages_extended_suite(client: Client, ctx: Any, reporter: Any) -> None:
    await client.connect(timeout=ctx.cfg.timeout)
    results: list[Any] = []
    resource_ids: dict[str, object] = {}

    reporter.audit_peer = await resolve_or_create_audit_peer(client, ctx, reporter)

    async def step_preview_and_effects() -> str:
        preview = await client.messages.web.preview(
            "https://telegram.org",
            timeout=ctx.cfg.timeout,
        )
        effects = await client.messages.effects.list(timeout=ctx.cfg.timeout)
        resource_ids["preview_type"] = type(preview).__name__
        resource_ids["effects_type"] = type(effects).__name__
        return f"preview={type(preview).__name__} effects={type(effects).__name__}"

    await run_step(
        name="messages_extended.roundtrip",
        fn=step_preview_and_effects,
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


def test_messages_extended__roundtrip__live_optional(
    client_v2: Client,
    live_context: Any,
    audit_reporter: Any,
) -> None:
    asyncio.run(_run_messages_extended_suite(client_v2, live_context, audit_reporter))
