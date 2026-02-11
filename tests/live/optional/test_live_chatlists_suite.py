from __future__ import annotations

import asyncio
import os
from typing import Any

import pytest

from telecraft.client import Client
from tests.live._suite_shared import finalize_run, resolve_or_create_audit_peer, run_step

pytestmark = [pytest.mark.live, pytest.mark.live_optional, pytest.mark.live_chatlists]


async def _run_chatlists_suite(client: Client, ctx: Any, reporter: Any) -> None:
    await client.connect(timeout=ctx.cfg.timeout)
    results: list[Any] = []
    resource_ids: dict[str, object] = {}

    reporter.audit_peer = await resolve_or_create_audit_peer(client, ctx, reporter)
    await reporter.emit(
        client=client,
        status="START",
        step="run",
        details=f"run_id={ctx.run_id} lane=optional-chatlists",
    )

    async def step_chatlists_roundtrip() -> str:
        slug = os.environ.get("TELECRAFT_LIVE_CHATLIST_SLUG", "").strip()
        if not slug:
            raise RuntimeError("Set TELECRAFT_LIVE_CHATLIST_SLUG to a valid chatlist invite slug")
        out = await client.chatlists.invites.check(slug, timeout=ctx.cfg.timeout)
        resource_ids["chatlists_check_type"] = type(out).__name__
        return f"chatlists_check={type(out).__name__}"

    await run_step(
        name="chatlists.roundtrip",
        fn=step_chatlists_roundtrip,
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


def test_chatlists_invites__check__roundtrip_live(
    client_v2: Client,
    live_context: Any,
    audit_reporter: Any,
) -> None:
    asyncio.run(_run_chatlists_suite(client_v2, live_context, audit_reporter))
