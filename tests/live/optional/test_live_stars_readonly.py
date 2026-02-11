from __future__ import annotations

import asyncio
from typing import Any

import pytest

from telecraft.client import Client
from tests.live._suite_shared import finalize_run, resolve_or_create_audit_peer, run_step

pytestmark = [pytest.mark.live, pytest.mark.live_optional]


async def _run_stars_readonly_suite(client: Client, ctx: Any, reporter: Any) -> None:
    await client.connect(timeout=ctx.cfg.timeout)
    results: list[Any] = []
    resource_ids: dict[str, object] = {}

    reporter.audit_peer = await resolve_or_create_audit_peer(client, ctx, reporter)
    await reporter.emit(
        client=client,
        status="START",
        step="run",
        details=f"run_id={ctx.run_id} lane=optional-stars-readonly",
    )

    async def step_stars_roundtrip() -> str:
        status = await client.stars.status(peer="self", timeout=ctx.cfg.timeout)
        topup = await client.stars.topup_options(timeout=ctx.cfg.timeout)
        tx = await client.stars.transactions.list(peer="self", limit=5, timeout=ctx.cfg.timeout)
        resource_ids["stars_status_type"] = type(status).__name__
        resource_ids["stars_topup_type"] = type(topup).__name__
        resource_ids["stars_tx_type"] = type(tx).__name__
        return (
            f"status={type(status).__name__} "
            f"topup={type(topup).__name__} tx={type(tx).__name__}"
        )

    await run_step(
        name="stars.roundtrip",
        fn=step_stars_roundtrip,
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


def test_stars__status__roundtrip_live(
    client_v2: Client,
    live_context: Any,
    audit_reporter: Any,
) -> None:
    asyncio.run(_run_stars_readonly_suite(client_v2, live_context, audit_reporter))
