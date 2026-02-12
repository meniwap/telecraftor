from __future__ import annotations

import asyncio
import os
from typing import Any

import pytest

from telecraft.client import Client, ReportReasonBuilder
from tests.live._suite_shared import finalize_run, resolve_or_create_audit_peer, run_step

pytestmark = [pytest.mark.live, pytest.mark.live_optional, pytest.mark.live_admin]


def _env(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


async def _run_reports_suite(client: Client, ctx: Any, reporter: Any) -> None:
    if not ctx.cfg.enable_admin:
        pytest.skip("Reports lane requires --live-admin")

    target_peer = _env("TELECRAFT_LIVE_REPORTS_PEER")
    if not target_peer:
        pytest.skip("Set TELECRAFT_LIVE_REPORTS_PEER to enable reports live lane")

    await client.connect(timeout=ctx.cfg.timeout)
    results: list[Any] = []
    resource_ids: dict[str, object] = {"target_peer": target_peer}

    reporter.audit_peer = await resolve_or_create_audit_peer(client, ctx, reporter)
    await reporter.emit(
        client=client,
        status="START",
        step="run",
        details=f"run_id={ctx.run_id} lane=optional-reports target={target_peer}",
    )

    async def step_report_peer() -> str:
        out = await client.reports.peer(
            target_peer,
            ReportReasonBuilder.other("telecraft_live_smoke"),
            message=f"telecraft live smoke {ctx.run_id}",
            timeout=ctx.cfg.timeout,
        )
        resource_ids["peer_report_type"] = type(out).__name__
        return f"reported={target_peer} type={type(out).__name__}"

    await run_step(
        name="reports.peer",
        fn=step_report_peer,
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


def test_reports__peer__roundtrip_live(
    client_v2: Client,
    live_context: Any,
    audit_reporter: Any,
) -> None:
    asyncio.run(_run_reports_suite(client_v2, live_context, audit_reporter))
