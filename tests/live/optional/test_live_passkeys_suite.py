from __future__ import annotations

import asyncio
from typing import Any

import pytest

from telecraft.client import Client
from tests.live._suite_shared import finalize_run, resolve_or_create_audit_peer, run_step

pytestmark = [pytest.mark.live, pytest.mark.live_optional, pytest.mark.live_passkeys]


async def _run_passkeys_suite(client: Client, ctx: Any, reporter: Any) -> None:
    await client.connect(timeout=ctx.cfg.timeout)
    results: list[Any] = []
    resource_ids: dict[str, object] = {}

    reporter.audit_peer = await resolve_or_create_audit_peer(client, ctx, reporter)

    async def step_passkeys_list() -> str:
        out = await client.account.passkeys.list(timeout=ctx.cfg.timeout)
        resource_ids["passkeys_type"] = type(out).__name__
        return f"passkeys={type(out).__name__}"

    await run_step(
        name="account_passkeys.list",
        fn=step_passkeys_list,
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


def test_account_passkeys__list__live_optional(
    client_v2: Client,
    live_context: Any,
    audit_reporter: Any,
) -> None:
    asyncio.run(_run_passkeys_suite(client_v2, live_context, audit_reporter))
