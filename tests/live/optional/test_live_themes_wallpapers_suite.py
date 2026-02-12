from __future__ import annotations

import asyncio
from typing import Any

import pytest

from telecraft.client import Client
from tests.live._suite_shared import (
    finalize_run,
    is_schema_decode_mismatch_error,
    resolve_or_create_audit_peer,
    run_step,
)

pytestmark = [pytest.mark.live, pytest.mark.live_optional]


async def _run_themes_wallpapers_suite(client: Client, ctx: Any, reporter: Any) -> None:
    await client.connect(timeout=ctx.cfg.timeout)
    results: list[Any] = []
    resource_ids: dict[str, object] = {}

    reporter.audit_peer = await resolve_or_create_audit_peer(client, ctx, reporter)
    await reporter.emit(
        client=client,
        status="START",
        step="run",
        details=f"run_id={ctx.run_id} lane=optional-themes-wallpapers",
    )

    async def step_themes_wallpapers() -> str:
        wallpapers = await client.account.wallpapers.list(timeout=ctx.cfg.timeout)
        resource_ids["wallpapers_type"] = type(wallpapers).__name__
        try:
            themes = await client.account.themes.list(timeout=ctx.cfg.timeout)
        except Exception as e:  # noqa: BLE001
            if not is_schema_decode_mismatch_error(e):
                raise
            resource_ids["themes_warning"] = f"{type(e).__name__}: {e}"
            return (
                "themes=unsupported(schema_mismatch) "
                f"wallpapers={type(wallpapers).__name__}"
            )
        resource_ids["themes_type"] = type(themes).__name__
        return f"themes={type(themes).__name__} wallpapers={type(wallpapers).__name__}"

    await run_step(
        name="account.themes_wallpapers",
        fn=step_themes_wallpapers,
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


def test_account_themes__list__roundtrip_live(
    client_v2: Client,
    live_context: Any,
    audit_reporter: Any,
) -> None:
    asyncio.run(_run_themes_wallpapers_suite(client_v2, live_context, audit_reporter))
