from __future__ import annotations

import asyncio
from typing import Any

import pytest

from telecraft.client import Client
from tests.live._suite_shared import finalize_run, resolve_or_create_audit_peer, run_step

pytestmark = [pytest.mark.live, pytest.mark.live_optional]


async def _run_contacts_requirements_suite(client: Client, ctx: Any, reporter: Any) -> None:
    await client.connect(timeout=ctx.cfg.timeout)
    results: list[Any] = []
    resource_ids: dict[str, object] = {}

    reporter.audit_peer = await resolve_or_create_audit_peer(client, ctx, reporter)

    async def step_to_contact() -> str:
        me = await client.profile.me(timeout=ctx.cfg.timeout)
        me_id = getattr(me, "id", None)
        if not isinstance(me_id, int):
            raise RuntimeError("profile.me() did not return a valid user id")
        out = await client.contacts.requirements.to_contact(
            [f"user:{me_id}"],
            timeout=ctx.cfg.timeout,
        )
        resource_ids["requirements_type"] = type(out).__name__
        return f"requirements={type(out).__name__}"

    await run_step(
        name="contacts_requirements.to_contact",
        fn=step_to_contact,
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


def test_contacts_requirements__to_contact__live_optional(
    client_v2: Client,
    live_context: Any,
    audit_reporter: Any,
) -> None:
    asyncio.run(_run_contacts_requirements_suite(client_v2, live_context, audit_reporter))
