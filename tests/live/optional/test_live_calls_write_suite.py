from __future__ import annotations

import asyncio
import os
from typing import Any

import pytest

from telecraft.client import Client
from tests.live._suite_shared import finalize_run, resolve_or_create_audit_peer, run_step

pytestmark = [
    pytest.mark.live,
    pytest.mark.live_optional,
    pytest.mark.live_calls_write,
    pytest.mark.destructive,
]


def _extract_call_ref(obj: Any) -> Any:
    call = getattr(obj, "call", None)
    if call is not None:
        return call
    updates = getattr(obj, "updates", None)
    if isinstance(updates, list):
        for item in updates:
            call_obj = getattr(item, "call", None)
            if call_obj is not None:
                return call_obj
    return None


async def _run_calls_write_suite(client: Client, ctx: Any, reporter: Any) -> None:
    if not ctx.cfg.enable_calls_write:
        pytest.skip("Calls write lane requires --live-calls-write")

    calls_peer = os.environ.get("TELECRAFT_LIVE_CALLS_WRITE_PEER", "").strip()
    if not calls_peer:
        pytest.skip("Set TELECRAFT_LIVE_CALLS_WRITE_PEER to enable calls write lane")

    await client.connect(timeout=ctx.cfg.timeout)
    results: list[Any] = []
    resource_ids: dict[str, object] = {"calls_peer": calls_peer}

    reporter.audit_peer = await resolve_or_create_audit_peer(client, ctx, reporter)
    await reporter.emit(
        client=client,
        status="START",
        step="run",
        details=f"run_id={ctx.run_id} lane=optional-calls-write peer={calls_peer}",
    )

    async def step_calls_create_discard() -> str:
        created = await client.calls.group.create(
            calls_peer,
            title=f"telecraft-call-{ctx.run_id}",
            timeout=ctx.cfg.timeout,
        )
        call_ref = _extract_call_ref(created)
        if call_ref is None:
            raise RuntimeError("call ref missing from create response")

        async def _cleanup() -> None:
            await client.calls.group.discard(call_ref, timeout=ctx.cfg.timeout)

        ctx.add_cleanup(_cleanup)
        discarded = await client.calls.group.discard(call_ref, timeout=ctx.cfg.timeout)
        resource_ids["create_type"] = type(created).__name__
        resource_ids["discard_type"] = type(discarded).__name__
        return f"create={type(created).__name__} discard={type(discarded).__name__}"

    await run_step(
        name="calls.group.create_discard",
        fn=step_calls_create_discard,
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


def test_calls_group__create__roundtrip_live(
    client_v2: Client,
    live_context: Any,
    audit_reporter: Any,
) -> None:
    asyncio.run(_run_calls_write_suite(client_v2, live_context, audit_reporter))
