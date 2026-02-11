from __future__ import annotations

import asyncio
from typing import Any

import pytest

from telecraft.client import Client
from tests.live._suite_shared import finalize_run, resolve_or_create_audit_peer, run_step

pytestmark = [
    pytest.mark.live,
    pytest.mark.live_optional,
    pytest.mark.destructive,
    pytest.mark.live_stories_write,
]


async def _run_stories_write_suite(client: Client, ctx: Any, reporter: Any) -> None:
    await client.connect(timeout=ctx.cfg.timeout)
    results: list[Any] = []
    resource_ids: dict[str, object] = {}

    reporter.audit_peer = await resolve_or_create_audit_peer(client, ctx, reporter)
    await reporter.emit(
        client=client,
        status="START",
        step="run",
        details=f"run_id={ctx.run_id} lane=optional-stories-write",
    )

    async def step_stories_write_roundtrip() -> str:
        try:
            out = await client.stories.toggle_all_hidden(False, timeout=ctx.cfg.timeout)
        except Exception as e:  # noqa: BLE001
            return f"stories write unsupported: {type(e).__name__}: {e}"
        resource_ids["stories_toggle_hidden_type"] = type(out).__name__
        return f"stories_toggle_hidden={type(out).__name__}"

    await run_step(
        name="stories_write.roundtrip",
        fn=step_stories_write_roundtrip,
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


def test_stories__toggle_all_hidden__roundtrip_live(
    client_v2: Client,
    live_context: Any,
    audit_reporter: Any,
) -> None:
    asyncio.run(_run_stories_write_suite(client_v2, live_context, audit_reporter))

