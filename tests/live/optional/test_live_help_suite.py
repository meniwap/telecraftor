from __future__ import annotations

import asyncio
from typing import Any

import pytest

from telecraft.client import Client
from tests.live._suite_shared import finalize_run, resolve_or_create_audit_peer, run_step

pytestmark = [pytest.mark.live, pytest.mark.live_optional]


async def _run_help_suite(client: Client, ctx: Any, reporter: Any) -> None:
    await client.connect(timeout=ctx.cfg.timeout)
    results: list[Any] = []
    resource_ids: dict[str, object] = {}

    reporter.audit_peer = await resolve_or_create_audit_peer(client, ctx, reporter)
    await reporter.emit(
        client=client,
        status="START",
        step="run",
        details=f"run_id={ctx.run_id} lane=optional-help",
    )

    async def step_help_roundtrip() -> str:
        cfg = await client.help.config(timeout=ctx.cfg.timeout)
        dc = await client.help.nearest_dc(timeout=ctx.cfg.timeout)
        resource_ids["config_type"] = type(cfg).__name__
        resource_ids["nearest_dc_type"] = type(dc).__name__
        return f"config={type(cfg).__name__} nearest_dc={type(dc).__name__}"

    await run_step(
        name="help.config",
        fn=step_help_roundtrip,
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


def test_help__config__roundtrip_live(
    client_v2: Client,
    live_context: Any,
    audit_reporter: Any,
) -> None:
    asyncio.run(_run_help_suite(client_v2, live_context, audit_reporter))
