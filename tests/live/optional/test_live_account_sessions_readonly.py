from __future__ import annotations

import asyncio
from typing import Any

import pytest

from telecraft.client import Client
from tests.live._suite_shared import finalize_run, resolve_or_create_audit_peer, run_step

pytestmark = [pytest.mark.live, pytest.mark.live_optional]


async def _run_account_readonly_suite(client: Client, ctx: Any, reporter: Any) -> None:
    await client.connect(timeout=ctx.cfg.timeout)
    results: list[Any] = []
    resource_ids: dict[str, object] = {}

    reporter.audit_peer = await resolve_or_create_audit_peer(client, ctx, reporter)
    await reporter.emit(
        client=client,
        status="START",
        step="run",
        details=f"run_id={ctx.run_id} lane=optional-account-readonly",
    )

    async def step_sessions() -> str:
        auth = await client.account.sessions.list(timeout=ctx.cfg.timeout)
        web = await client.account.web_sessions.list(timeout=ctx.cfg.timeout)
        content = await client.account.content.get(timeout=ctx.cfg.timeout)
        ttl = await client.account.ttl.get_default(timeout=ctx.cfg.timeout)
        resource_ids["authorizations_type"] = type(auth).__name__
        resource_ids["web_authorizations_type"] = type(web).__name__
        resource_ids["content_type"] = type(content).__name__
        resource_ids["ttl_type"] = type(ttl).__name__
        return (
            f"auth={type(auth).__name__} web={type(web).__name__} "
            f"content={type(content).__name__} ttl={type(ttl).__name__}"
        )

    await run_step(
        name="account.readonly",
        fn=step_sessions,
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


def test_account_sessions__list__roundtrip_live(
    client_v2: Client,
    live_context: Any,
    audit_reporter: Any,
) -> None:
    asyncio.run(_run_account_readonly_suite(client_v2, live_context, audit_reporter))
