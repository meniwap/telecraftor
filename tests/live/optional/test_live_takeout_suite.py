from __future__ import annotations

import asyncio
from typing import Any

import pytest

from telecraft.client import Client, TakeoutScopes
from tests.live._suite_shared import finalize_run, resolve_or_create_audit_peer, run_step

pytestmark = [pytest.mark.live, pytest.mark.live_optional, pytest.mark.live_takeout]


async def _run_takeout_suite(client: Client, ctx: Any, reporter: Any) -> None:
    if not ctx.cfg.enable_takeout:
        pytest.skip("Takeout lane requires --live-takeout")

    await client.connect(timeout=ctx.cfg.timeout)
    results: list[Any] = []
    resource_ids: dict[str, object] = {}

    reporter.audit_peer = await resolve_or_create_audit_peer(client, ctx, reporter)
    await reporter.emit(
        client=client,
        status="START",
        step="run",
        details=f"run_id={ctx.run_id} lane=optional-takeout",
    )

    async def step_takeout_roundtrip() -> str:
        started = await client.takeout.start(
            TakeoutScopes(
                contacts=False,
                message_users=True,
                message_chats=False,
                message_megagroups=False,
                message_channels=False,
                files=False,
            ),
            timeout=ctx.cfg.timeout,
        )

        async def _cleanup() -> None:
            await client.takeout.finish(success=False, timeout=ctx.cfg.timeout)

        ctx.add_cleanup(_cleanup)

        exported = await client.takeout.messages.export(
            str(reporter.audit_peer),
            limit=1,
            timeout=ctx.cfg.timeout,
        )
        finished = await client.takeout.finish(success=True, timeout=ctx.cfg.timeout)

        resource_ids["start_type"] = type(started).__name__
        resource_ids["export_type"] = type(exported).__name__
        resource_ids["finish_type"] = type(finished).__name__
        return (
            f"start={type(started).__name__} "
            f"export={type(exported).__name__} finish={type(finished).__name__}"
        )

    await run_step(
        name="takeout.roundtrip",
        fn=step_takeout_roundtrip,
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


def test_takeout__start__roundtrip_live(
    client_v2: Client,
    live_context: Any,
    audit_reporter: Any,
) -> None:
    asyncio.run(_run_takeout_suite(client_v2, live_context, audit_reporter))
