from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from telecraft.client import Client
from tests.live._suite_shared import (
    extract_channel_id,
    extract_message_id,
    finalize_run,
    is_private_or_not_found_error,
    resolve_or_create_audit_peer,
    run_step,
)

pytestmark = [pytest.mark.live, pytest.mark.destructive, pytest.mark.live_core]


async def _run_core_suite(
    *,
    client: Client,
    ctx: Any,
    reporter: Any,
    force_failure: bool,
) -> None:
    if not ctx.cfg.destructive:
        pytest.skip("Core live suite requires --live-destructive")

    await client.connect(timeout=ctx.cfg.timeout)
    results: list[Any] = []
    resource_ids: dict[str, object] = {}

    audit_peer = await resolve_or_create_audit_peer(client, ctx, reporter)
    reporter.audit_peer = audit_peer
    await reporter.emit(
        client=client,
        status="START",
        step="run",
        details=f"run_id={ctx.run_id} lane=core",
    )

    source_channel: dict[str, object] = {}
    target_channel: dict[str, object] = {}

    async def step_create_resources() -> str:
        src = await client.chats.create_channel(
            title=f"tc-v3-core-src-{ctx.run_id}",
            about="Telecraft V3 core live test channel",
            broadcast=False,
            megagroup=True,
            timeout=ctx.cfg.timeout,
        )
        src_id = extract_channel_id(src)
        if src_id is None:
            raise RuntimeError("Could not extract source channel id")
        source_channel["peer"] = f"channel:{src_id}"
        resource_ids["source_channel"] = src_id

        dst = await client.chats.create_channel(
            title=f"tc-v3-core-dst-{ctx.run_id}",
            about="Telecraft V3 core live test destination channel",
            broadcast=False,
            megagroup=True,
            timeout=ctx.cfg.timeout,
        )
        dst_id = extract_channel_id(dst)
        if dst_id is None:
            raise RuntimeError("Could not extract target channel id")
        target_channel["peer"] = f"channel:{dst_id}"
        resource_ids["target_channel"] = dst_id

        async def _cleanup_dst() -> None:
            try:
                await client.chats.delete_channel(f"channel:{dst_id}", timeout=ctx.cfg.timeout)
            except Exception as e:  # noqa: BLE001
                if is_private_or_not_found_error(e):
                    return
                raise

        async def _cleanup_src() -> None:
            try:
                await client.chats.delete_channel(f"channel:{src_id}", timeout=ctx.cfg.timeout)
            except Exception as e:  # noqa: BLE001
                if is_private_or_not_found_error(e):
                    return
                raise

        ctx.add_cleanup(_cleanup_dst)
        ctx.add_cleanup(_cleanup_src)
        return f"source={src_id} target={dst_id}"

    await run_step(
        name="resources.create",
        fn=step_create_resources,
        client=client,
        reporter=reporter,
        results=results,
    )

    async def step_messages_roundtrip() -> str:
        source_peer = str(source_channel["peer"])
        target_peer = str(target_channel["peer"])

        sent = await client.messages.send(
            source_peer,
            f"core live {ctx.run_id}",
            timeout=ctx.cfg.timeout,
        )
        sent_id = extract_message_id(sent)
        if sent_id is None:
            raise RuntimeError("send did not return message id")

        await client.messages.edit(
            source_peer,
            sent_id,
            f"core edited {ctx.run_id}",
            timeout=ctx.cfg.timeout,
        )
        await client.messages.pin(source_peer, sent_id, timeout=ctx.cfg.timeout)
        await client.messages.pin(source_peer, sent_id, unpin=True, timeout=ctx.cfg.timeout)
        await client.messages.react(source_peer, sent_id, reaction="👍", timeout=ctx.cfg.timeout)

        forwarded = await client.messages.forward(
            from_peer=source_peer,
            to_peer=target_peer,
            msg_ids=[sent_id],
            timeout=ctx.cfg.timeout,
        )
        forwarded_id = extract_message_id(forwarded)
        await client.messages.delete(source_peer, sent_id, revoke=True, timeout=ctx.cfg.timeout)

        return f"sent={sent_id} forwarded={forwarded_id}"

    await run_step(
        name="messages.roundtrip",
        fn=step_messages_roundtrip,
        client=client,
        reporter=reporter,
        results=results,
    )

    async def step_invites_lifecycle() -> str:
        channel_peer = str(source_channel["peer"])
        inv = await client.chats.invites.create(
            channel_peer,
            usage_limit=3,
            title="core-suite",
            timeout=ctx.cfg.timeout,
        )
        link = getattr(inv, "link", None)
        if isinstance(link, bytes):
            link = link.decode("utf-8", "replace")
        if not isinstance(link, str) or not link:
            raise RuntimeError("Invite link missing")

        listed = await client.chats.invites.list(channel_peer, limit=10, timeout=ctx.cfg.timeout)
        await client.chats.invites.revoke(channel_peer, link, timeout=ctx.cfg.timeout)
        await client.chats.invites.delete(channel_peer, link, timeout=ctx.cfg.timeout)
        total = len(getattr(listed, "invites", []) or [])
        return f"link={link} listed={total}"

    await run_step(
        name="invites.lifecycle",
        fn=step_invites_lifecycle,
        client=client,
        reporter=reporter,
        results=results,
    )

    if force_failure:

        async def step_intentional_fail() -> str:
            raise RuntimeError("intentional failure for cleanup verification")

        await run_step(
            name="cleanup.verify",
            fn=step_intentional_fail,
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


def test_messages__send__roundtrip_live(
    client_v2: Client,
    live_context: Any,
    audit_reporter: Any,
) -> None:
    asyncio.run(
        _run_core_suite(
            client=client_v2,
            ctx=live_context,
            reporter=audit_reporter,
            force_failure=False,
        )
    )


def test_chats__create_channel__cleanup_on_failure(
    client_v2: Client,
    live_context: Any,
    audit_reporter: Any,
) -> None:
    try:
        asyncio.run(
            _run_core_suite(
                client=client_v2,
                ctx=live_context,
                reporter=audit_reporter,
                force_failure=True,
            )
        )
    except AssertionError:
        artifacts_path = Path(live_context.run_dir) / "artifacts.json"
        assert artifacts_path.exists()
        artifacts = json.loads(artifacts_path.read_text(encoding="utf-8"))
        assert "cleanup_errors" in artifacts
        return
    raise AssertionError("Expected forced failure to validate cleanup_on_failure flow")
