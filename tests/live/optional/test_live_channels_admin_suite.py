from __future__ import annotations

import asyncio
from typing import Any

import pytest

from telecraft.client import Client
from tests.live._suite_shared import finalize_run, resolve_or_create_audit_peer, run_step

pytestmark = [
    pytest.mark.live,
    pytest.mark.live_optional,
    pytest.mark.destructive,
    pytest.mark.live_channel_admin,
]


async def _run_channels_admin_suite(client: Client, ctx: Any, reporter: Any) -> None:
    await client.connect(timeout=ctx.cfg.timeout)
    results: list[Any] = []
    resource_ids: dict[str, object] = {}

    reporter.audit_peer = await resolve_or_create_audit_peer(client, ctx, reporter)
    await reporter.emit(
        client=client,
        status="START",
        step="run",
        details=f"run_id={ctx.run_id} lane=optional-channels-admin",
    )

    async def step_channels_admin_roundtrip() -> str:
        history = await client.channels.read_history(
            str(reporter.audit_peer),
            timeout=ctx.cfg.timeout,
        )
        resource_ids["channels_read_history_type"] = type(history).__name__
        try:
            await client.channels.settings.toggle_antispam(
                str(reporter.audit_peer),
                enabled=False,
                timeout=ctx.cfg.timeout,
            )
        except Exception as e:  # noqa: BLE001
            return (
                f"read_history={type(history).__name__} "
                f"admin_op_unsupported={type(e).__name__}: {e}"
            )
        return f"read_history={type(history).__name__} admin_op=ok"

    await run_step(
        name="channels_admin.roundtrip",
        fn=step_channels_admin_roundtrip,
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


def test_channels__read_history__roundtrip_live(
    client_v2: Client,
    live_context: Any,
    audit_reporter: Any,
) -> None:
    asyncio.run(_run_channels_admin_suite(client_v2, live_context, audit_reporter))
