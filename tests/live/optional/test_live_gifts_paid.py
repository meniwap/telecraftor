from __future__ import annotations

import asyncio
import os
from typing import Any

import pytest

from telecraft.client import Client, GiftRef
from tests.live._suite_shared import finalize_run, resolve_or_create_audit_peer, run_step

pytestmark = [pytest.mark.live, pytest.mark.live_optional, pytest.mark.live_paid]


async def _run_gifts_paid_suite(client: Client, ctx: Any, reporter: Any, msg_id: int) -> None:
    await client.connect(timeout=ctx.cfg.timeout)
    results: list[Any] = []
    resource_ids: dict[str, object] = {}

    reporter.audit_peer = await resolve_or_create_audit_peer(client, ctx, reporter)
    await reporter.emit(
        client=client,
        status="START",
        step="run",
        details=f"run_id={ctx.run_id} lane=optional-gifts-paid",
    )

    async def step_gifts_paid_save_unsave() -> str:
        ref = GiftRef.user_msg(msg_id)
        await client.gifts.saved.save(ref, unsave=False, timeout=ctx.cfg.timeout)
        await client.gifts.saved.save(ref, unsave=True, timeout=ctx.cfg.timeout)
        resource_ids["gift_ref_msg_id"] = msg_id
        return f"msg_id={msg_id}"

    await run_step(
        name="gifts.paid.save_unsave",
        fn=step_gifts_paid_save_unsave,
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


def test_gifts_saved__save__roundtrip_live(
    client_v2: Client,
    live_context: Any,
    audit_reporter: Any,
) -> None:
    if not live_context.cfg.enable_paid:
        pytest.skip("Paid live suite requires --live-paid")

    msg_id_raw = os.environ.get("TELECRAFT_LIVE_PAID_GIFT_MSG_ID", "").strip()
    if not msg_id_raw:
        pytest.skip("Set TELECRAFT_LIVE_PAID_GIFT_MSG_ID to a gift source message id")
    try:
        msg_id = int(msg_id_raw)
    except ValueError as e:
        raise pytest.UsageError("TELECRAFT_LIVE_PAID_GIFT_MSG_ID must be an int") from e

    asyncio.run(_run_gifts_paid_suite(client_v2, live_context, audit_reporter, msg_id))
