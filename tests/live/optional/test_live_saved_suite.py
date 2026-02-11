from __future__ import annotations

import asyncio
from typing import Any

import pytest

from telecraft.client import Client
from tests.live._suite_shared import finalize_run, resolve_or_create_audit_peer, run_step

pytestmark = [pytest.mark.live, pytest.mark.live_optional]


async def _run_saved_suite(client: Client, ctx: Any, reporter: Any) -> None:
    await client.connect(timeout=ctx.cfg.timeout)
    results: list[Any] = []
    resource_ids: dict[str, object] = {}

    reporter.audit_peer = await resolve_or_create_audit_peer(client, ctx, reporter)
    await reporter.emit(
        client=client,
        status="START",
        step="run",
        details=f"run_id={ctx.run_id} lane=optional-saved",
    )

    async def step_saved_roundtrip() -> str:
        dialogs = await client.saved.dialogs.list(limit=10, timeout=ctx.cfg.timeout)
        gifs = await client.saved.gifs.list(timeout=ctx.cfg.timeout)
        tags = await client.saved.reaction_tags.list(timeout=ctx.cfg.timeout)
        resource_ids["saved_dialogs_type"] = type(dialogs).__name__
        resource_ids["saved_gifs_type"] = type(gifs).__name__
        resource_ids["saved_tags_type"] = type(tags).__name__
        return (
            f"dialogs={type(dialogs).__name__} "
            f"gifs={type(gifs).__name__} tags={type(tags).__name__}"
        )

    await run_step(
        name="saved.roundtrip",
        fn=step_saved_roundtrip,
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


def test_saved__dialogs__roundtrip_live(
    client_v2: Client,
    live_context: Any,
    audit_reporter: Any,
) -> None:
    asyncio.run(_run_saved_suite(client_v2, live_context, audit_reporter))
