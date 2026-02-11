from __future__ import annotations

import asyncio
import json
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
]


def _require_second_account(ctx: Any) -> None:
    if not ctx.cfg.second_account:
        pytest.skip("Second-account lane requires --live-second-account <username>")


def _is_tolerable_add_error(err: Exception) -> bool:
    msg = str(err).upper()
    return any(
        token in msg
        for token in (
            "USER_NOT_MUTUAL_CONTACT",
            "USER_PRIVACY_RESTRICTED",
            "USER_CHANNELS_TOO_MUCH",
            "USER_ALREADY_PARTICIPANT",
        )
    )


async def _run_membership_suite(
    *,
    client: Client,
    ctx: Any,
    reporter: Any,
    method_name: str,
    force_failure: bool,
) -> None:
    _require_second_account(ctx)
    if not ctx.cfg.destructive:
        pytest.skip("Second-account lane requires --live-destructive")

    await client.connect(timeout=ctx.cfg.timeout)
    results: list[Any] = []
    resource_ids: dict[str, object] = {}

    reporter.audit_peer = await resolve_or_create_audit_peer(client, ctx, reporter)
    await reporter.emit(
        client=client,
        status="START",
        step="run",
        details=f"run_id={ctx.run_id} lane=second_account second={ctx.cfg.second_account}",
    )

    second_peer = await client.peers.resolve(ctx.cfg.second_account, timeout=ctx.cfg.timeout)
    second_user_id = parse_user_id(second_peer)
    resource_ids["second_account_user_id"] = second_user_id

    target_channel: dict[str, object] = {}

    async def step_create_group() -> str:
        channel = await client.chats.create_channel(
            title=f"tc-v3-membership-{ctx.run_id}",
            about="Telecraft V3 second-account lane",
            broadcast=False,
            megagroup=True,
            timeout=ctx.cfg.timeout,
        )
        cid = extract_channel_id(channel)
        if cid is None:
            raise RuntimeError("Could not extract channel id from create_channel result")
        target_channel["peer"] = f"channel:{cid}"
        resource_ids["target_channel"] = cid

        async def _cleanup_group() -> None:
            await client.chats.delete_channel(f"channel:{cid}", timeout=ctx.cfg.timeout)

        ctx.add_cleanup(_cleanup_group)
        return f"channel={cid}"

    await run_step(
        name="resources.create",
        fn=step_create_group,
        client=client,
        reporter=reporter,
        results=results,
    )

    async def step_roundtrip() -> str:
        group_peer = str(target_channel["peer"])
        note = "ok"
        if method_name == "add":
            try:
                await client.chats.members.remove(
                    group_peer,
                    ctx.cfg.second_account,
                    timeout=ctx.cfg.timeout,
                )
            except Exception:  # noqa: BLE001
                pass
            try:
                await client.chats.members.add(
                    group_peer,
                    ctx.cfg.second_account,
                    timeout=ctx.cfg.timeout,
                )
            except Exception as e:  # noqa: BLE001
                if _is_tolerable_add_error(e):
                    note = f"add-skipped:{type(e).__name__}"
                else:
                    raise
        elif method_name == "remove":
            try:
                await client.chats.members.add(
                    group_peer,
                    ctx.cfg.second_account,
                    timeout=ctx.cfg.timeout,
                )
            except Exception:  # noqa: BLE001
                pass
            await client.chats.members.remove(
                group_peer,
                ctx.cfg.second_account,
                timeout=ctx.cfg.timeout,
            )
        else:
            raise AssertionError(f"Unknown method_name={method_name!r}")
        members = await client.chats.members.list(group_peer, limit=200, timeout=ctx.cfg.timeout)
        count = len(members)
        return f"method={method_name} members={count} user_id={second_user_id} note={note}"

    await run_step(
        name=f"members.{method_name}.roundtrip",
        fn=step_roundtrip,
        client=client,
        reporter=reporter,
        results=results,
    )

    if force_failure:

        async def step_intentional_failure() -> str:
            raise RuntimeError("intentional failure for cleanup verification")

        await run_step(
            name=f"members.{method_name}.cleanup",
            fn=step_intentional_failure,
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


def test_chats_members__add__roundtrip_live(
    client_v2: Client,
    live_context: Any,
    audit_reporter: Any,
) -> None:
    asyncio.run(
        _run_membership_suite(
            client=client_v2,
            ctx=live_context,
            reporter=audit_reporter,
            method_name="add",
            force_failure=False,
        )
    )


def test_chats_members__remove__roundtrip_live(
    client_v2: Client,
    live_context: Any,
    audit_reporter: Any,
) -> None:
    asyncio.run(
        _run_membership_suite(
            client=client_v2,
            ctx=live_context,
            reporter=audit_reporter,
            method_name="remove",
            force_failure=False,
        )
    )


def test_chats_members__add__cleanup_on_failure(
    client_v2: Client,
    live_context: Any,
    audit_reporter: Any,
) -> None:
    try:
        asyncio.run(
            _run_membership_suite(
                client=client_v2,
                ctx=live_context,
                reporter=audit_reporter,
                method_name="add",
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


def test_chats_members__remove__cleanup_on_failure(
    client_v2: Client,
    live_context: Any,
    audit_reporter: Any,
) -> None:
    try:
        asyncio.run(
            _run_membership_suite(
                client=client_v2,
                ctx=live_context,
                reporter=audit_reporter,
                method_name="remove",
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
