from __future__ import annotations

import asyncio
from typing import Any

import pytest

from telecraft.client import Client
from tests.live._suite_shared import finalize_run, resolve_or_create_audit_peer, run_step

pytestmark = [pytest.mark.live, pytest.mark.live_optional]


async def _run_account_identity_suite(client: Client, ctx: Any, reporter: Any) -> None:
    await client.connect(timeout=ctx.cfg.timeout)
    results: list[Any] = []
    resource_ids: dict[str, object] = {}

    reporter.audit_peer = await resolve_or_create_audit_peer(client, ctx, reporter)

    async def step_identity_readonly() -> str:
        check = await client.account.identity.check_username(
            "telecraft_test_name",
            timeout=ctx.cfg.timeout,
        )
        candidates = await client.account.personal_channel.candidates(timeout=ctx.cfg.timeout)
        resource_ids["check_type"] = type(check).__name__
        resource_ids["candidates_type"] = type(candidates).__name__
        return f"check={type(check).__name__} candidates={type(candidates).__name__}"

    await run_step(
        name="account_identity.roundtrip",
        fn=step_identity_readonly,
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


def test_account_identity__roundtrip__live_optional(
    client_v2: Client,
    live_context: Any,
    audit_reporter: Any,
) -> None:
    asyncio.run(_run_account_identity_suite(client_v2, live_context, audit_reporter))
