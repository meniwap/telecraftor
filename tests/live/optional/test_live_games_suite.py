from __future__ import annotations

import asyncio
from typing import Any

import pytest

from telecraft.client import Client
from tests.live._suite_shared import (
    extract_message_id,
    finalize_run,
    resolve_or_create_audit_peer,
    run_step,
)

pytestmark = [pytest.mark.live, pytest.mark.live_optional]


async def _run_games_suite(client: Client, ctx: Any, reporter: Any) -> None:
    await client.connect(timeout=ctx.cfg.timeout)
    results: list[Any] = []
    resource_ids: dict[str, object] = {}

    reporter.audit_peer = await resolve_or_create_audit_peer(client, ctx, reporter)
    await reporter.emit(
        client=client,
        status="START",
        step="run",
        details=f"run_id={ctx.run_id} lane=optional-games",
    )

    async def step_games_roundtrip() -> str:
        out = await client.games.roll_dice(str(reporter.audit_peer), timeout=ctx.cfg.timeout)
        msg_id = extract_message_id(out)
        if msg_id is None:
            raise RuntimeError("games.roll_dice did not return message id")
        resource_ids["dice_msg_id"] = msg_id
        return f"dice_msg_id={msg_id}"

    await run_step(
        name="games.roundtrip",
        fn=step_games_roundtrip,
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


def test_games__send__roundtrip_live(
    client_v2: Client,
    live_context: Any,
    audit_reporter: Any,
) -> None:
    asyncio.run(_run_games_suite(client_v2, live_context, audit_reporter))
