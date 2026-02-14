from __future__ import annotations

import asyncio
from typing import Any

import pytest

from telecraft.client import Client
from tests.live._suite_shared import finalize_run, resolve_or_create_audit_peer, run_step

pytestmark = [pytest.mark.live, pytest.mark.live_optional, pytest.mark.live_premium]


async def _run_premium_boosts_suite(client: Client, ctx: Any, reporter: Any) -> None:
    await client.connect(timeout=ctx.cfg.timeout)
    results: list[Any] = []
    resource_ids: dict[str, object] = {}

    reporter.audit_peer = await resolve_or_create_audit_peer(client, ctx, reporter)

    async def step_boosts_readonly() -> str:
        peer = reporter.audit_peer
        my_boosts = await client.premium.boosts.my(timeout=ctx.cfg.timeout)
        status = await client.premium.boosts.status(peer, timeout=ctx.cfg.timeout)
        listed = await client.premium.boosts.list(peer, timeout=ctx.cfg.timeout)
        resource_ids["my_type"] = type(my_boosts).__name__
        resource_ids["status_type"] = type(status).__name__
        resource_ids["list_type"] = type(listed).__name__
        return (
            f"my={type(my_boosts).__name__} "
            f"status={type(status).__name__} "
            f"list={type(listed).__name__}"
        )

    await run_step(
        name="premium_boosts.readonly",
        fn=step_boosts_readonly,
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


def test_premium_boosts__readonly__live_optional(
    client_v2: Client,
    live_context: Any,
    audit_reporter: Any,
) -> None:
    asyncio.run(_run_premium_boosts_suite(client_v2, live_context, audit_reporter))
