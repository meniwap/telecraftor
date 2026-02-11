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


async def _run_optional_polls(client: Client, ctx: Any, reporter: Any) -> None:
    if not ctx.cfg.enable_polls:
        pytest.skip("Optional polls lane requires --live-enable-polls")

    await client.connect(timeout=ctx.cfg.timeout)
    results: list[Any] = []
    resource_ids: dict[str, object] = {}

    reporter.audit_peer = await resolve_or_create_audit_peer(client, ctx, reporter)
    await reporter.emit(
        client=client,
        status="START",
        step="run",
        details=f"run_id={ctx.run_id} lane=optional-polls",
    )

    async def step_polls_roundtrip() -> str:
        peer = str(reporter.audit_peer)
        poll = await client.polls.send(
            peer,
            question=f"Telecraft optional poll {ctx.run_id}?",
            options=["yes", "no"],
            timeout=ctx.cfg.timeout,
        )
        poll_mid = extract_message_id(poll)
        if poll_mid is None:
            raise RuntimeError("poll message id missing")

        await client.polls.vote(peer, msg_id=poll_mid, options=0, timeout=ctx.cfg.timeout)
        _ = await client.polls.results(peer, msg_id=poll_mid, timeout=ctx.cfg.timeout)
        close_note = "closed"
        try:
            await client.polls.close(peer, msg_id=poll_mid, timeout=ctx.cfg.timeout)
        except Exception as e:  # noqa: BLE001
            if ctx.cfg.enable_strict_polls_close:
                raise
            close_note = f"close-warning:{type(e).__name__}"
            await reporter.emit(
                client=client,
                status="WARN",
                step="polls.close",
                details=f"poll_msg={poll_mid} close_failed={type(e).__name__}: {e}",
            )
        resource_ids["poll_msg_id"] = poll_mid
        resource_ids["poll_close_status"] = close_note
        return f"poll_msg={poll_mid} {close_note}"

    await run_step(
        name="polls.roundtrip",
        fn=step_polls_roundtrip,
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


def test_polls__send__roundtrip_live(
    client_v2: Client,
    live_context: Any,
    audit_reporter: Any,
) -> None:
    asyncio.run(_run_optional_polls(client_v2, live_context, audit_reporter))
