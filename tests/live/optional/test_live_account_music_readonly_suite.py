from __future__ import annotations

import asyncio
from typing import Any

import pytest

from telecraft.client import Client
from tests.live._suite_shared import finalize_run, resolve_or_create_audit_peer, run_step

pytestmark = [pytest.mark.live, pytest.mark.live_optional]


async def _run_account_music_suite(client: Client, ctx: Any, reporter: Any) -> None:
    await client.connect(timeout=ctx.cfg.timeout)
    results: list[Any] = []
    resource_ids: dict[str, object] = {}

    reporter.audit_peer = await resolve_or_create_audit_peer(client, ctx, reporter)

    async def step_music_and_gift_themes() -> str:
        saved_ids = await client.account.music.saved_ids(timeout=ctx.cfg.timeout)
        gift_themes = await client.account.gift_themes.list(timeout=ctx.cfg.timeout)
        resource_ids["saved_ids_type"] = type(saved_ids).__name__
        resource_ids["gift_themes_type"] = type(gift_themes).__name__
        return (
            f"saved_ids={type(saved_ids).__name__} "
            f"gift_themes={type(gift_themes).__name__}"
        )

    await run_step(
        name="account_music.readonly",
        fn=step_music_and_gift_themes,
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


def test_account_music__readonly__live_optional(
    client_v2: Client,
    live_context: Any,
    audit_reporter: Any,
) -> None:
    asyncio.run(_run_account_music_suite(client_v2, live_context, audit_reporter))
