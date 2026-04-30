from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from telecraft.client import Client
from tests.live._suite_shared import (
    extract_channel_id,
    finalize_run,
    parse_user_id,
    resolve_or_create_audit_peer,
    run_step,
)

pytestmark = [
    pytest.mark.live,
    pytest.mark.destructive,
    pytest.mark.requires_second_account,
    pytest.mark.live_second_account,
    pytest.mark.live_admin,
]


def _require_second_account_admin_lane(ctx: Any) -> None:
    if not ctx.cfg.second_account:
        pytest.skip("Second-account admin lane requires --live-second-account <username>")
    if not ctx.cfg.destructive:
        pytest.skip("Second-account admin lane requires --live-destructive")
    if not ctx.cfg.enable_admin:
        pytest.skip("Second-account admin lane requires --live-admin")


async def _run_admin_moderation_suite(client: Client, ctx: Any, reporter: Any) -> None:
    _require_second_account_admin_lane(ctx)

    await client.connect(timeout=ctx.cfg.timeout)
    results: list[Any] = []
    resource_ids: dict[str, object] = {}

    reporter.audit_peer = await resolve_or_create_audit_peer(client, ctx, reporter)
    await reporter.emit(
        client=client,
        status="START",
        step="run",
        details=f"run_id={ctx.run_id} lane=second-account-admin second={ctx.cfg.second_account}",
    )

    second_peer = await client.peers.resolve(ctx.cfg.second_account, timeout=ctx.cfg.timeout)
    second_user_id = parse_user_id(second_peer)
    resource_ids["second_account_user_id"] = second_user_id
    target_channel: dict[str, object] = {}

    async def step_create_group() -> str:
        channel = await client.chats.create_channel(
            title=f"tc-v3-admin-{ctx.run_id}",
            about="Telecraft second-account admin hardening lane",
            broadcast=False,
            megagroup=True,
            timeout=ctx.cfg.timeout,
        )
        cid = extract_channel_id(channel)
        if cid is None:
            raise RuntimeError("Could not extract channel id from create_channel result")
        group_peer = f"channel:{cid}"
        target_channel["peer"] = group_peer
        resource_ids["target_channel"] = cid

        async def _cleanup_second_user_state() -> None:
            try:
                await client.admin.demote(
                    group_peer,
                    ctx.cfg.second_account,
                    timeout=ctx.cfg.timeout,
                )
            except Exception:  # noqa: BLE001
                pass
            try:
                await client.admin.unban(
                    group_peer,
                    ctx.cfg.second_account,
                    timeout=ctx.cfg.timeout,
                )
            except Exception:  # noqa: BLE001
                pass

        async def _cleanup_group() -> None:
            await client.chats.delete_channel(group_peer, timeout=ctx.cfg.timeout)

        ctx.add_cleanup(_cleanup_group)
        ctx.add_cleanup(_cleanup_second_user_state)
        return f"channel={cid}"

    await run_step(
        name="resources.create",
        fn=step_create_group,
        client=client,
        reporter=reporter,
        results=results,
    )

    async def step_promote_demote_roundtrip() -> str:
        group_peer = str(target_channel["peer"])
        await client.chats.members.add(group_peer, ctx.cfg.second_account, timeout=ctx.cfg.timeout)
        await client.admin.promote(
            group_peer,
            ctx.cfg.second_account,
            delete_messages=True,
            ban_users=True,
            invite_users=True,
            pin_messages=False,
            rank="tc-test",
            timeout=ctx.cfg.timeout,
        )
        promoted = await client.admin.member(
            group_peer,
            ctx.cfg.second_account,
            timeout=ctx.cfg.timeout,
        )
        await client.admin.demote(group_peer, ctx.cfg.second_account, timeout=ctx.cfg.timeout)
        demoted = await client.admin.member(
            group_peer,
            ctx.cfg.second_account,
            timeout=ctx.cfg.timeout,
        )
        resource_ids["promoted_member_type"] = type(promoted).__name__
        resource_ids["demoted_member_type"] = type(demoted).__name__
        return f"promoted={type(promoted).__name__} demoted={type(demoted).__name__}"

    await run_step(
        name="admin.promote_demote.roundtrip",
        fn=step_promote_demote_roundtrip,
        client=client,
        reporter=reporter,
        results=results,
    )

    async def step_ban_unban_kick_roundtrip() -> str:
        group_peer = str(target_channel["peer"])
        try:
            await client.chats.members.add(
                group_peer,
                ctx.cfg.second_account,
                timeout=ctx.cfg.timeout,
            )
        except Exception:  # noqa: BLE001
            pass
        await client.admin.ban(group_peer, ctx.cfg.second_account, timeout=ctx.cfg.timeout)
        await client.admin.unban(group_peer, ctx.cfg.second_account, timeout=ctx.cfg.timeout)
        try:
            await client.chats.members.add(
                group_peer,
                ctx.cfg.second_account,
                timeout=ctx.cfg.timeout,
            )
        except Exception:  # noqa: BLE001
            pass
        await client.admin.kick(group_peer, ctx.cfg.second_account, timeout=ctx.cfg.timeout)
        await client.admin.unban(group_peer, ctx.cfg.second_account, timeout=ctx.cfg.timeout)
        return "ban_unban_kick=ok"

    await run_step(
        name="admin.ban_unban_kick.roundtrip",
        fn=step_ban_unban_kick_roundtrip,
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


def test_admin__moderation__rollback_roundtrip_live(
    client_v2: Client,
    live_context: Any,
    audit_reporter: Any,
) -> None:
    asyncio.run(_run_admin_moderation_suite(client_v2, live_context, audit_reporter))


def test_admin__moderation__cleanup_policy_documented() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    assert "ctx.add_cleanup(_cleanup_second_user_state)" in source
    assert "ctx.add_cleanup(_cleanup_group)" in source
