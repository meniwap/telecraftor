from __future__ import annotations

import asyncio
import os
from typing import Any

import pytest

from telecraft.client import Client
from tests.live._suite_shared import finalize_run, resolve_or_create_audit_peer, run_step

pytestmark = [pytest.mark.live, pytest.mark.live_optional, pytest.mark.live_webapps]


async def _run_webapps_suite(client: Client, ctx: Any, reporter: Any) -> None:
    if not ctx.cfg.enable_webapps:
        pytest.skip("WebApps lane requires --live-webapps")

    bot = os.environ.get("TELECRAFT_LIVE_WEBAPP_BOT", "").strip()
    if not bot:
        pytest.skip("Set TELECRAFT_LIVE_WEBAPP_BOT to enable webapps live lane")

    await client.connect(timeout=ctx.cfg.timeout)
    results: list[Any] = []
    resource_ids: dict[str, object] = {"bot": bot}

    reporter.audit_peer = await resolve_or_create_audit_peer(client, ctx, reporter)
    await reporter.emit(
        client=client,
        status="START",
        step="run",
        details=f"run_id={ctx.run_id} lane=optional-webapps bot={bot}",
    )

    async def step_webapps_roundtrip() -> str:
        out = await client.webapps.request(
            peer=str(reporter.audit_peer),
            bot=bot,
            platform="android",
            timeout=ctx.cfg.timeout,
        )
        resource_ids["request_type"] = type(out).__name__
        return f"request={type(out).__name__}"

    await run_step(
        name="webapps.request",
        fn=step_webapps_roundtrip,
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


def test_webapps__request__roundtrip_live(
    client_v2: Client,
    live_context: Any,
    audit_reporter: Any,
) -> None:
    asyncio.run(_run_webapps_suite(client_v2, live_context, audit_reporter))
