from __future__ import annotations

import asyncio
from typing import Any

import pytest

from telecraft.client import Client, NotifyTarget
from tests.live._suite_shared import finalize_run, resolve_or_create_audit_peer, run_step

pytestmark = [pytest.mark.live, pytest.mark.live_optional]


async def _run_privacy_notifications_suite(client: Client, ctx: Any, reporter: Any) -> None:
    await client.connect(timeout=ctx.cfg.timeout)
    results: list[Any] = []
    resource_ids: dict[str, object] = {}

    reporter.audit_peer = await resolve_or_create_audit_peer(client, ctx, reporter)
    await reporter.emit(
        client=client,
        status="START",
        step="run",
        details=f"run_id={ctx.run_id} lane=optional-privacy-notifications",
    )

    async def step_privacy_notifications_roundtrip() -> str:
        privacy = await client.privacy.get("status_timestamp", timeout=ctx.cfg.timeout)
        notify = await client.notifications.get(NotifyTarget.users(), timeout=ctx.cfg.timeout)
        resource_ids["privacy_type"] = type(privacy).__name__
        resource_ids["notify_type"] = type(notify).__name__
        return f"privacy={type(privacy).__name__} notifications={type(notify).__name__}"

    await run_step(
        name="privacy_notifications.roundtrip",
        fn=step_privacy_notifications_roundtrip,
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


def test_privacy_notifications__get__roundtrip_live(
    client_v2: Client,
    live_context: Any,
    audit_reporter: Any,
) -> None:
    asyncio.run(_run_privacy_notifications_suite(client_v2, live_context, audit_reporter))

