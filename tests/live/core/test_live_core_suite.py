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

pytestmark = [pytest.mark.live, pytest.mark.live_core]


async def _run_core_suite(
    *,
    client: Client,
    ctx: Any,
    reporter: Any,
    force_failure: bool,
    require_destructive_flag: bool,
) -> None:
    safe_mode = not require_destructive_flag
    if require_destructive_flag and not ctx.cfg.destructive:
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
    msg_state: dict[str, object] = {}

    async def step_create_resources() -> str:
        if safe_mode:
            source_channel["peer"] = audit_peer
            target_channel["peer"] = audit_peer
            resource_ids["source_peer"] = audit_peer
            resource_ids["target_peer"] = audit_peer
            return f"using_audit_peer={audit_peer}"

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
        if not safe_mode:
            await client.messages.pin(source_peer, sent_id, timeout=ctx.cfg.timeout)
            await client.messages.pin(source_peer, sent_id, unpin=True, timeout=ctx.cfg.timeout)
            await client.messages.react(
                source_peer,
                sent_id,
                reaction="👍",
                timeout=ctx.cfg.timeout,
            )

        forwarded_id: int | None = None
        if not safe_mode:
            forwarded = await client.messages.forward(
                from_peer=source_peer,
                to_peer=target_peer,
                msg_ids=[sent_id],
                timeout=ctx.cfg.timeout,
            )
            forwarded_id = extract_message_id(forwarded)
            if forwarded_id is None:
                raise RuntimeError("forward did not return message id")

        msg_state["source_peer"] = source_peer
        msg_state["target_peer"] = target_peer
        msg_state["sent_id"] = sent_id
        msg_state["forwarded_id"] = forwarded_id

        if safe_mode:
            return f"sent={sent_id} forwarded=skipped(audit_peer)"
        return f"sent={sent_id} forwarded={forwarded_id}"

    await run_step(
        name="messages.roundtrip",
        fn=step_messages_roundtrip,
        client=client,
        reporter=reporter,
        results=results,
    )

    async def step_messages_verify_state() -> str:
        if "source_peer" not in msg_state:
            return "skipped_missing_state_after_messages.roundtrip_failure"

        source_peer = str(msg_state["source_peer"])
        target_peer = str(msg_state["target_peer"])
        sent_id = int(msg_state["sent_id"])
        forwarded_id_raw = msg_state.get("forwarded_id")

        source_history = await client.messages.history(
            source_peer,
            limit=10,
            timeout=ctx.cfg.timeout,
        )
        target_history: list[Any] = []
        if not safe_mode:
            target_history = await client.messages.history(
                target_peer,
                limit=10,
                timeout=ctx.cfg.timeout,
            )
        search_results = await client.messages.search(
            source_peer,
            query=f"core edited {ctx.run_id}",
            limit=10,
            timeout=ctx.cfg.timeout,
        )
        dialog_peers = [source_peer] if safe_mode else [source_peer, target_peer]
        dialogs_by_peers = await client.dialogs.by_peers(dialog_peers, timeout=ctx.cfg.timeout)

        mark_read_id = sent_id if safe_mode else int(forwarded_id_raw)
        await client.messages.mark_read(target_peer, max_id=mark_read_id, timeout=ctx.cfg.timeout)

        src_hit = any(getattr(m, "id", None) == sent_id for m in source_history)
        dst_hit = True
        if not safe_mode:
            if forwarded_id_raw is None:
                raise RuntimeError("forwarded id missing in destructive core flow")
            dst_hit = any(getattr(m, "id", None) == int(forwarded_id_raw) for m in target_history)
        if not source_history and not safe_mode:
            raise RuntimeError("source history returned no messages")
        if not dst_hit:
            raise RuntimeError(f"forwarded message {forwarded_id_raw} not found in target history")

        resource_ids["source_history_count"] = len(source_history)
        resource_ids["target_history_count"] = len(target_history)
        resource_ids["search_result_count"] = len(search_results)
        resource_ids["dialogs_by_peers_type"] = type(dialogs_by_peers).__name__
        return (
            f"source_history={len(source_history)} "
            f"target_history={len(target_history)} "
            f"source_hit={src_hit} "
            f"target_hit={dst_hit} "
            f"search={len(search_results)} "
            f"dialogs={type(dialogs_by_peers).__name__}"
        )

    await run_step(
        name="messages.verify_state",
        fn=step_messages_verify_state,
        client=client,
        reporter=reporter,
        results=results,
    )

    async def step_messages_cleanup() -> str:
        if "source_peer" not in msg_state:
            return "skipped_missing_state_after_messages.roundtrip_failure"

        source_peer = str(msg_state["source_peer"])
        target_peer = str(msg_state["target_peer"])
        sent_id = int(msg_state["sent_id"])
        forwarded_id_raw = msg_state.get("forwarded_id")

        if forwarded_id_raw is not None:
            await client.messages.delete(
                target_peer,
                int(forwarded_id_raw),
                revoke=True,
                timeout=ctx.cfg.timeout,
            )
        await client.messages.delete(
            source_peer,
            sent_id,
            revoke=True,
            timeout=ctx.cfg.timeout,
        )
        return f"deleted sent={sent_id} forwarded={forwarded_id_raw}"

    await run_step(
        name="messages.cleanup",
        fn=step_messages_cleanup,
        client=client,
        reporter=reporter,
        results=results,
    )

    if not safe_mode:

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

            listed = await client.chats.invites.list(
                channel_peer,
                limit=10,
                timeout=ctx.cfg.timeout,
            )
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


@pytest.mark.live_core_safe
def test_messages__send__roundtrip_live(
    client_v2: Client,
    live_context: Any,
    audit_reporter: Any,
) -> None:
    # Reversible flow (create/send/edit/forward/delete + cleanup) used as core-safe smoke.
    asyncio.run(
        _run_core_suite(
            client=client_v2,
            ctx=live_context,
            reporter=audit_reporter,
            force_failure=False,
            require_destructive_flag=False,
        )
    )


@pytest.mark.live_core_destructive
@pytest.mark.destructive
def test_chats__create_channel__cleanup_on_failure(
    client_v2: Client,
    live_context: Any,
    audit_reporter: Any,
) -> None:
    # Forced failure path validates cleanup behavior and is destructive-gated.
    try:
        asyncio.run(
            _run_core_suite(
                client=client_v2,
                ctx=live_context,
                reporter=audit_reporter,
                force_failure=True,
                require_destructive_flag=True,
            )
        )
    except AssertionError:
        artifacts_path = Path(live_context.run_dir) / "artifacts.json"
        assert artifacts_path.exists()
        artifacts = json.loads(artifacts_path.read_text(encoding="utf-8"))
        assert "cleanup_errors" in artifacts
        return
    raise AssertionError("Expected forced failure to validate cleanup_on_failure flow")
