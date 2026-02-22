from __future__ import annotations

import asyncio
import os
from typing import Any

import pytest

from telecraft.client import Client
from tests.live._suite_shared import finalize_run, resolve_or_create_audit_peer, run_step

pytestmark = [pytest.mark.live, pytest.mark.live_optional]


async def _run_auth_suite(client: Client, ctx: Any, reporter: Any) -> None:
    if os.environ.get("TELECRAFT_LIVE_AUTH_ENABLE", "").strip() != "1":
        pytest.skip("Set TELECRAFT_LIVE_AUTH_ENABLE=1 to enable optional auth live suite")

    await client.connect(timeout=ctx.cfg.timeout)
    results: list[Any] = []
    resource_ids: dict[str, object] = {}

    reporter.audit_peer = await resolve_or_create_audit_peer(client, ctx, reporter)
    await reporter.emit(
        client=client,
        status="START",
        step="run",
        details=f"run_id={ctx.run_id} lane=optional-auth",
    )

    async def step_auth_export_login_token_roundtrip() -> str:
        out = await client.auth.export_login_token(timeout=ctx.cfg.timeout)
        resource_ids["export_login_token_type"] = type(out).__name__
        return f"export_login_token={type(out).__name__}"

    await run_step(
        name="auth.export_login_token",
        fn=step_auth_export_login_token_roundtrip,
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


def test_auth__export_login_token__roundtrip_live(
    client_v2: Client,
    live_context: Any,
    audit_reporter: Any,
) -> None:
    asyncio.run(_run_auth_suite(client_v2, live_context, audit_reporter))
