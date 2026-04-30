from __future__ import annotations

import asyncio
from typing import Any

import pytest

from telecraft.client import Client
from tests.live._suite_shared import finalize_run, resolve_live_audit_peer, run_step

pytestmark = [pytest.mark.live, pytest.mark.live_prod_safe]


async def _run_core_suite(client: Client, ctx: Any, reporter: Any) -> None:
    await client.connect(timeout=ctx.cfg.timeout)
    results: list[Any] = []
    resource_ids: dict[str, object] = {}
    reporter.audit_peer = resolve_live_audit_peer(ctx)

    await reporter.emit(
        client=client,
        status="START",
        step="run",
        details=f"run_id={ctx.run_id} lane=core_prod_safe",
    )

    async def step_identity() -> str:
        me = await client.profile.me(timeout=ctx.cfg.timeout)
        resource_ids["me_type"] = type(me).__name__
        return f"me_id={getattr(me, 'id', None)!r} type={type(me).__name__}"

    await run_step(
        name="identity.profile",
        fn=step_identity,
        client=client,
        reporter=reporter,
        results=results,
    )

    async def step_help_config() -> str:
        cfg = await client.help.config(timeout=ctx.cfg.timeout)
        nearest_dc = await client.help.nearest_dc(timeout=ctx.cfg.timeout)
        resource_ids["help_config_type"] = type(cfg).__name__
        resource_ids["nearest_dc_type"] = type(nearest_dc).__name__
        return f"config={type(cfg).__name__} nearest_dc={type(nearest_dc).__name__}"

    await run_step(
        name="help.config",
        fn=step_help_config,
        client=client,
        reporter=reporter,
        results=results,
    )

    async def step_dialogs_readonly() -> str:
        dialogs = await client.dialogs.list(limit=1, timeout=ctx.cfg.timeout)
        resource_ids["dialogs_type"] = type(dialogs).__name__
        return f"dialogs={type(dialogs).__name__}"

    await run_step(
        name="dialogs.readonly",
        fn=step_dialogs_readonly,
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


def test_live_core_suite__prod_safe_smoke(
    client_v2: Client,
    live_context: Any,
    audit_reporter: Any,
) -> None:
    asyncio.run(_run_core_suite(client_v2, live_context, audit_reporter))
