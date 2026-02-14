from __future__ import annotations

import asyncio
from typing import Any

import pytest

from telecraft.client import Client
from tests.live._suite_shared import finalize_run, resolve_or_create_audit_peer, run_step

pytestmark = [pytest.mark.live, pytest.mark.live_optional]


async def _run_messages_announcements_suite(client: Client, ctx: Any, reporter: Any) -> None:
    await client.connect(timeout=ctx.cfg.timeout)
    results: list[Any] = []
    resource_ids: dict[str, object] = {}

    reporter.audit_peer = await resolve_or_create_audit_peer(client, ctx, reporter)

    async def step_saved_tags_and_attach_menu() -> str:
        defaults = await client.messages.saved_tags.defaults(timeout=ctx.cfg.timeout)
        attach_bots = await client.messages.attach_menu.bots(timeout=ctx.cfg.timeout)
        resource_ids["saved_tags_type"] = type(defaults).__name__
        resource_ids["attach_menu_type"] = type(attach_bots).__name__
        return (
            f"saved_tags={type(defaults).__name__} "
            f"attach_menu={type(attach_bots).__name__}"
        )

    await run_step(
        name="messages_announcements.readonly",
        fn=step_saved_tags_and_attach_menu,
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


def test_messages_announcements__readonly__live_optional(
    client_v2: Client,
    live_context: Any,
    audit_reporter: Any,
) -> None:
    asyncio.run(_run_messages_announcements_suite(client_v2, live_context, audit_reporter))
