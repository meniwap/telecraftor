from __future__ import annotations

import asyncio
from typing import Any

import pytest

from telecraft.client import Client
from tests.live._suite_shared import finalize_run, resolve_live_audit_peer, run_step

pytestmark = [pytest.mark.live, pytest.mark.live_prod_safe]


async def _run_prod_safe_baseline(client: Client, ctx: Any, reporter: Any) -> None:
    await client.connect(timeout=ctx.cfg.timeout)
    results: list[Any] = []
    resource_ids: dict[str, object] = {}
    reporter.audit_peer = resolve_live_audit_peer(ctx)

    async def step_identity_profile() -> str:
        me = await client.profile.me(timeout=ctx.cfg.timeout)
        defaults = await client.profile.emoji_status.defaults(timeout=ctx.cfg.timeout)
        recent = await client.profile.emoji_status.recent(timeout=ctx.cfg.timeout)

        resource_ids["me_type"] = type(me).__name__
        resource_ids["profile_defaults_type"] = type(defaults).__name__
        resource_ids["profile_recent_type"] = type(recent).__name__
        return (
            f"me_id={getattr(me, 'id', None)!r} "
            f"defaults={type(defaults).__name__} recent={type(recent).__name__}"
        )

    await run_step(
        name="identity.profile",
        fn=step_identity_profile,
        client=client,
        reporter=reporter,
        results=results,
    )

    async def step_dialogs_readonly() -> str:
        dialogs = await client.dialogs.list(limit=1, timeout=ctx.cfg.timeout)
        filters = await client.dialogs.filters.list(timeout=ctx.cfg.timeout)
        suggested = await client.dialogs.filters.suggested(timeout=ctx.cfg.timeout)

        resource_ids["dialogs_type"] = type(dialogs).__name__
        resource_ids["dialog_filters_type"] = type(filters).__name__
        resource_ids["dialog_suggested_filters_type"] = type(suggested).__name__
        return (
            f"dialogs={type(dialogs).__name__} "
            f"filters={type(filters).__name__} suggested={type(suggested).__name__}"
        )

    await run_step(
        name="dialogs.readonly",
        fn=step_dialogs_readonly,
        client=client,
        reporter=reporter,
        results=results,
    )

    async def step_messages_discovery() -> str:
        search_global = await client.search.global_messages(limit=1, timeout=ctx.cfg.timeout)
        saved_tags = await client.messages.saved_tags.defaults(timeout=ctx.cfg.timeout)
        attach_menu = await client.messages.attach_menu.bots(timeout=ctx.cfg.timeout)

        resource_ids["search_global_type"] = type(search_global).__name__
        resource_ids["saved_tags_type"] = type(saved_tags).__name__
        resource_ids["attach_menu_type"] = type(attach_menu).__name__
        return (
            f"global={type(search_global).__name__} "
            f"saved_tags={type(saved_tags).__name__} attach_menu={type(attach_menu).__name__}"
        )

    await run_step(
        name="messages.discovery",
        fn=step_messages_discovery,
        client=client,
        reporter=reporter,
        results=results,
    )

    async def step_stickers_reactions() -> str:
        stickers = await client.stickers.sets.all(timeout=ctx.cfg.timeout)
        featured = await client.stickers.sets.featured(timeout=ctx.cfg.timeout)
        recent_reactions = await client.reactions.recent(limit=20, timeout=ctx.cfg.timeout)

        resource_ids["stickers_type"] = type(stickers).__name__
        resource_ids["featured_stickers_type"] = type(featured).__name__
        resource_ids["recent_reactions_type"] = type(recent_reactions).__name__
        return (
            f"stickers={type(stickers).__name__} "
            f"featured={type(featured).__name__} reactions={type(recent_reactions).__name__}"
        )

    await run_step(
        name="stickers.reactions",
        fn=step_stickers_reactions,
        client=client,
        reporter=reporter,
        results=results,
    )

    async def step_saved_surface() -> str:
        saved_dialogs = await client.saved.dialogs.list(limit=5, timeout=ctx.cfg.timeout)
        saved_gifs = await client.saved.gifs.list(timeout=ctx.cfg.timeout)
        reaction_tags = await client.saved.reaction_tags.list(timeout=ctx.cfg.timeout)

        resource_ids["saved_dialogs_type"] = type(saved_dialogs).__name__
        resource_ids["saved_gifs_type"] = type(saved_gifs).__name__
        resource_ids["saved_reaction_tags_type"] = type(reaction_tags).__name__
        return (
            f"dialogs={type(saved_dialogs).__name__} "
            f"gifs={type(saved_gifs).__name__} tags={type(reaction_tags).__name__}"
        )

    await run_step(
        name="saved.surface",
        fn=step_saved_surface,
        client=client,
        reporter=reporter,
        results=results,
    )

    async def step_account_appearance() -> str:
        gift_themes = await client.account.gift_themes.list(limit=5, timeout=ctx.cfg.timeout)
        music_ids = await client.account.music.saved_ids(timeout=ctx.cfg.timeout)
        themes = await client.account.themes.list(timeout=ctx.cfg.timeout)
        wallpapers = await client.account.wallpapers.list(timeout=ctx.cfg.timeout)

        resource_ids["gift_themes_type"] = type(gift_themes).__name__
        resource_ids["music_ids_type"] = type(music_ids).__name__
        resource_ids["themes_type"] = type(themes).__name__
        resource_ids["wallpapers_type"] = type(wallpapers).__name__
        return (
            f"gift_themes={type(gift_themes).__name__} "
            f"music_ids={type(music_ids).__name__} "
            f"themes={type(themes).__name__} wallpapers={type(wallpapers).__name__}"
        )

    await run_step(
        name="account.appearance",
        fn=step_account_appearance,
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

    await finalize_run(
        client=client,
        ctx=ctx,
        reporter=reporter,
        results=results,
        resource_ids=resource_ids,
    )


def test_live_prod_safe_baseline__roundtrip(
    client_v2: Client,
    live_context: Any,
    audit_reporter: Any,
) -> None:
    asyncio.run(_run_prod_safe_baseline(client_v2, live_context, audit_reporter))
