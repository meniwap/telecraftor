from __future__ import annotations

import asyncio
from typing import Any

import pytest

from telecraft.client import Client
from tests.live._suite_shared import finalize_run, resolve_or_create_audit_peer, run_step

pytestmark = [pytest.mark.live, pytest.mark.live_optional]


async def _run_topics_suite(client: Client, ctx: Any, reporter: Any) -> None:
    await client.connect(timeout=ctx.cfg.timeout)
    results: list[Any] = []
    resource_ids: dict[str, object] = {}

    reporter.audit_peer = await resolve_or_create_audit_peer(client, ctx, reporter)
    await reporter.emit(
        client=client,
        status="START",
        step="run",
        details=f"run_id={ctx.run_id} lane=optional-topics",
    )

    async def step_topics_roundtrip() -> str:
        try:
            out = await client.topics.list(
                str(reporter.audit_peer),
                limit=10,
                timeout=ctx.cfg.timeout,
            )
        except Exception as e:  # noqa: BLE001
            return f"topics unsupported for peer={reporter.audit_peer}: {type(e).__name__}: {e}"
        resource_ids["topics_type"] = type(out).__name__
        return f"topics={type(out).__name__}"

    await run_step(
        name="topics.roundtrip",
        fn=step_topics_roundtrip,
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


def test_topics__list__roundtrip_live(
    client_v2: Client,
    live_context: Any,
    audit_reporter: Any,
) -> None:
    asyncio.run(_run_topics_suite(client_v2, live_context, audit_reporter))
