from __future__ import annotations

import asyncio
from typing import Any

import pytest

from telecraft.client import Client
from tests.live._suite_shared import (
    create_temp_write_peer,
    finalize_run,
    is_chat_write_forbidden_error,
    resolve_or_create_audit_peer,
    run_step,
)

pytestmark = [pytest.mark.live, pytest.mark.live_optional]


async def _run_drafts_suite(client: Client, ctx: Any, reporter: Any) -> None:
    await client.connect(timeout=ctx.cfg.timeout)
    results: list[Any] = []
    resource_ids: dict[str, object] = {}

    reporter.audit_peer = await resolve_or_create_audit_peer(client, ctx, reporter)
    await reporter.emit(
        client=client,
        status="START",
        step="run",
        details=f"run_id={ctx.run_id} lane=optional-drafts",
    )

    async def step_drafts_roundtrip() -> str:
        peer = str(reporter.audit_peer)
        try:
            await client.drafts.save(peer, text=f"draft {ctx.run_id}", timeout=ctx.cfg.timeout)
        except Exception as e:  # noqa: BLE001
            if not is_chat_write_forbidden_error(e):
                raise
            peer = await create_temp_write_peer(
                client=client,
                ctx=ctx,
                resource_ids=resource_ids,
                key_prefix="drafts",
            )
            await client.drafts.save(peer, text=f"draft {ctx.run_id}", timeout=ctx.cfg.timeout)

        current = await client.drafts.get(peer, timeout=ctx.cfg.timeout)
        await client.drafts.clear(peer, timeout=ctx.cfg.timeout)
        resource_ids["draft_peer"] = peer
        resource_ids["draft_get_type"] = type(current).__name__
        return f"peer={peer} draft_get={type(current).__name__}"

    await run_step(
        name="drafts.roundtrip",
        fn=step_drafts_roundtrip,
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


def test_drafts__save__roundtrip_live(
    client_v2: Client,
    live_context: Any,
    audit_reporter: Any,
) -> None:
    asyncio.run(_run_drafts_suite(client_v2, live_context, audit_reporter))
