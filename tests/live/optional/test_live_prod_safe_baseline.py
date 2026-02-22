from __future__ import annotations

import asyncio
from typing import Any

import pytest

from telecraft.client import Client
from tests.live._suite_shared import finalize_run, resolve_or_create_audit_peer, run_step

pytestmark = [pytest.mark.live, pytest.mark.live_optional, pytest.mark.live_prod_safe]


async def _run_prod_safe_baseline(client: Client, ctx: Any, reporter: Any) -> None:
    await client.connect(timeout=ctx.cfg.timeout)
    results: list[Any] = []
    resource_ids: dict[str, object] = {}

    reporter.audit_peer = await resolve_or_create_audit_peer(client, ctx, reporter)

    async def step_prod_safe_readonly() -> str:
        me = await client.profile.me(timeout=ctx.cfg.timeout)
        dialogs = await client.dialogs.list(limit=1, timeout=ctx.cfg.timeout)
        saved_tags = await client.messages.saved_tags.defaults(timeout=ctx.cfg.timeout)
        attach_menu = await client.messages.attach_menu.bots(timeout=ctx.cfg.timeout)
        search_global = await client.search.global_messages(limit=1, timeout=ctx.cfg.timeout)
        stickers = await client.stickers.sets.all(timeout=ctx.cfg.timeout)
        saved_dialogs = await client.saved.dialogs.list(limit=5, timeout=ctx.cfg.timeout)
        gift_themes = await client.account.gift_themes.list(limit=5, timeout=ctx.cfg.timeout)
        music_ids = await client.account.music.saved_ids(timeout=ctx.cfg.timeout)
        themes = await client.account.themes.list(timeout=ctx.cfg.timeout)
        wallpapers = await client.account.wallpapers.list(timeout=ctx.cfg.timeout)

        resource_ids["me_type"] = type(me).__name__
        resource_ids["dialogs_type"] = type(dialogs).__name__
        resource_ids["saved_tags_type"] = type(saved_tags).__name__
        resource_ids["attach_menu_type"] = type(attach_menu).__name__
        resource_ids["search_global_type"] = type(search_global).__name__
        resource_ids["stickers_type"] = type(stickers).__name__
        resource_ids["saved_dialogs_type"] = type(saved_dialogs).__name__
        resource_ids["gift_themes_type"] = type(gift_themes).__name__
        resource_ids["music_ids_type"] = type(music_ids).__name__
        resource_ids["themes_type"] = type(themes).__name__
        resource_ids["wallpapers_type"] = type(wallpapers).__name__

        me_id = getattr(me, "id", None)
        return f"me_id={me_id!r} dialogs={type(dialogs).__name__} themes={type(themes).__name__}"

    await run_step(
        name="prod_safe_baseline.readonly",
        fn=step_prod_safe_readonly,
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


def test_live_prod_safe_baseline__roundtrip__live_optional(
    client_v2: Client,
    live_context: Any,
    audit_reporter: Any,
) -> None:
    asyncio.run(_run_prod_safe_baseline(client_v2, live_context, audit_reporter))
