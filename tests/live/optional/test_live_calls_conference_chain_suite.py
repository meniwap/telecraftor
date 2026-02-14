from __future__ import annotations

import asyncio
import os
from typing import Any

import pytest

from telecraft.client import Client, GroupCallRef
from tests.live._suite_shared import finalize_run, resolve_or_create_audit_peer, run_step

pytestmark = [pytest.mark.live, pytest.mark.live_optional, pytest.mark.live_calls]


async def _run_calls_chain_suite(client: Client, ctx: Any, reporter: Any) -> None:
    await client.connect(timeout=ctx.cfg.timeout)
    results: list[Any] = []
    resource_ids: dict[str, object] = {}

    reporter.audit_peer = await resolve_or_create_audit_peer(client, ctx, reporter)

    async def step_chain_blocks() -> str:
        call_id = os.environ.get("TELECRAFT_LIVE_GROUP_CALL_ID", "").strip()
        access_hash = os.environ.get("TELECRAFT_LIVE_GROUP_CALL_ACCESS_HASH", "").strip()
        sub_chain_id = os.environ.get("TELECRAFT_LIVE_GROUP_CALL_SUB_CHAIN_ID", "").strip()
        if not call_id or not access_hash or not sub_chain_id:
            return "skipped_missing_env=TELECRAFT_LIVE_GROUP_CALL_ID/ACCESS_HASH/SUB_CHAIN_ID"

        out = await client.calls.group.chain.blocks(
            GroupCallRef.from_parts(int(call_id), int(access_hash)),
            int(sub_chain_id),
            timeout=ctx.cfg.timeout,
        )
        resource_ids["chain_blocks_type"] = type(out).__name__
        return f"chain_blocks={type(out).__name__}"

    await run_step(
        name="calls_conference_chain.blocks",
        fn=step_chain_blocks,
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


def test_calls_conference_chain__blocks__live_optional(
    client_v2: Client,
    live_context: Any,
    audit_reporter: Any,
) -> None:
    asyncio.run(_run_calls_chain_suite(client_v2, live_context, audit_reporter))
