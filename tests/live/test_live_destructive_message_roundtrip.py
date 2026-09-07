from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import pytest

from telecraft.client import Client
from telecraft.client.mtproto import MtprotoClientError
from tests.live._destructive_message import (
    DESTRUCTIVE_MESSAGE_PROFILE,
    MessageUpdateNotObserved,
    ObservedMessageUpdate,
    extract_sent_message_id,
    find_exact_message,
    message_id_and_text,
    wait_for_exact_message_update,
)
from tests.live._suite_shared import finalize_run, run_step

pytestmark = [pytest.mark.live, pytest.mark.live_destructive]


@dataclass(slots=True)
class _MessageState:
    send_attempted: bool = False
    message_id: int | None = None


async def _observe_exact_message_update(
    *,
    client: Client,
    expected_text: str,
    expected_id: int | None,
    timeout: float,
) -> ObservedMessageUpdate:
    """Observe the sent update, forcing one bounded startup catch-up when needed."""

    async def observe() -> ObservedMessageUpdate:
        observer = asyncio.create_task(
            wait_for_exact_message_update(
                client.updates.recv,
                expected_text=expected_text,
                expected_id=expected_id,
                timeout=timeout,
            )
        )
        try:
            # Give a server-pushed update a short opportunity first. If Telegram
            # returns the update only as the originating RPC result, restarting
            # from the pre-send checkpoint forces updates.getDifference instead.
            done, _ = await asyncio.wait(
                {observer},
                timeout=min(1.0, timeout / 4),
            )
            if observer in done:
                try:
                    return observer.result()
                except MessageUpdateNotObserved:
                    pass

            await client.updates.stop()

            observed_before_restart: ObservedMessageUpdate | None = None
            try:
                # stop() terminates an empty receiver, but recv_update drains
                # every already accepted queue item before surfacing that
                # intentional terminal condition.
                observed_before_restart = await observer
            except MtprotoClientError as exc:
                if str(exc) != "Updates stopped":
                    raise
            except MessageUpdateNotObserved:
                pass

            await client.updates.start(timeout=timeout)
            if observed_before_restart is not None:
                return observed_before_restart
            return await wait_for_exact_message_update(
                client.updates.recv,
                expected_text=expected_text,
                expected_id=expected_id,
                timeout=timeout,
            )
        finally:
            if not observer.done():
                observer.cancel()
                try:
                    await observer
                except asyncio.CancelledError:
                    pass

    try:
        return await asyncio.wait_for(observe(), timeout=timeout)
    except asyncio.TimeoutError as exc:
        raise MessageUpdateNotObserved(
            f"Exact test-message update was not observed within {float(timeout):.1f}s"
        ) from exc


async def _assert_update_stream_healthy(client: Client, *, dwell: float = 0.25) -> None:
    """Fail on an already-terminal update stream without logging any queued payload."""

    if not client.is_connected:
        raise AssertionError("MTProto connection became unhealthy during update validation")
    waiter = asyncio.create_task(client.updates.recv())
    try:
        done, _ = await asyncio.wait({waiter}, timeout=dwell)
        if waiter in done:
            _ = waiter.result()
    finally:
        if not waiter.done():
            waiter.cancel()
            try:
                await waiter
            except asyncio.CancelledError:
                pass


def _exact_message_id(
    messages: list[Any],
    *,
    expected_texts: tuple[str, ...],
    expected_id: int | None = None,
) -> int | None:
    candidates: set[int] = set()
    for message in messages:
        identity = message_id_and_text(message)
        if identity is None:
            continue
        message_id, text = identity
        if text in expected_texts and (expected_id is None or message_id == expected_id):
            candidates.add(message_id)
    if len(candidates) == 1:
        return next(iter(candidates))
    return None


async def _locate_exact_message(
    *,
    client: Client,
    peer: str,
    token: str,
    expected_text: str,
    expected_id: int | None,
    timeout: float,
) -> Any:
    for attempt in range(3):
        history = await client.messages.history(peer, limit=50, timeout=timeout)
        message = find_exact_message(
            history,
            expected_text=expected_text,
            expected_id=expected_id,
        )
        if message is not None:
            return message

        search = await client.messages.search(
            peer,
            query=token,
            limit=20,
            timeout=timeout,
        )
        message = find_exact_message(
            search,
            expected_text=expected_text,
            expected_id=expected_id,
        )
        if message is not None:
            return message
        if attempt < 2:
            await asyncio.sleep(0.75)
    raise AssertionError(
        f"Exact test-created message was not observable (id={expected_id!r}, token={token})"
    )


async def _run_destructive_message_roundtrip(
    client: Client,
    ctx: Any,
    reporter: Any,
    *,
    peer: str,
) -> None:
    results: list[Any] = []
    token = f"telecraftlive_{uuid4().hex}"
    initial_text = f"Telecraft destructive live check {token} initial"
    edited_text = f"Telecraft destructive live check {token} edited"
    state = _MessageState()
    resource_ids: dict[str, object] = {
        "message_token": token,
        "destructive_peer": peer,
        "cleanup_revoke": "pending",
        "updates_engine": "pending",
    }
    rpc_timeout = min(float(ctx.cfg.timeout), 10.0)
    cleanup_timeout = min(float(ctx.cfg.timeout), 4.0)
    update_timeout = min(float(ctx.cfg.timeout), 15.0)

    async def cleanup_created_message() -> None:
        if not state.send_attempted:
            resource_ids["cleanup_revoke"] = "not_needed"
            return

        message_id = state.message_id
        if message_id is None:
            history = await client.messages.history(
                peer,
                limit=50,
                timeout=cleanup_timeout,
            )
            message_id = _exact_message_id(
                history,
                expected_texts=(initial_text, edited_text),
            )
        if message_id is None:
            search = await client.messages.search(
                peer,
                query=token,
                limit=20,
                timeout=cleanup_timeout,
            )
            message_id = _exact_message_id(
                search,
                expected_texts=(initial_text, edited_text),
            )
        if message_id is None:
            raise RuntimeError(
                "Cleanup could not uniquely locate the exact test-created message; "
                f"manual recovery token={token} peer={peer}"
            )

        state.message_id = message_id
        resource_ids["message_id"] = message_id
        await client.messages.delete(
            peer,
            message_id,
            revoke=True,
            timeout=cleanup_timeout,
        )

        history = await client.messages.history(
            peer,
            limit=50,
            timeout=cleanup_timeout,
        )
        if (
            _exact_message_id(
                history,
                expected_texts=(initial_text, edited_text),
                expected_id=message_id,
            )
            is not None
        ):
            raise RuntimeError(
                f"Revoked message is still visible in history (id={message_id}, token={token})"
            )
        resource_ids["cleanup_revoke"] = "confirmed"

    # Register cleanup before the first write. If send times out after Telegram accepted it,
    # cleanup falls back to the unique token and exact text rather than guessing an ID.
    ctx.add_cleanup(cleanup_created_message)
    reporter.audit_peer = None

    try:
        await client.connect(timeout=ctx.cfg.timeout)

        async def step_start_updates() -> str:
            await asyncio.wait_for(
                client.updates.start(timeout=rpc_timeout),
                timeout=rpc_timeout,
            )
            if not client.is_connected:
                raise AssertionError("MTProto connection is unhealthy after update startup")
            resource_ids["updates_engine"] = "started"
            return "updates engine initialized on a healthy connection"

        await run_step(
            name="updates.destructive.start",
            fn=step_start_updates,
            client=client,
            reporter=reporter,
            results=results,
        )
        if not results or results[-1].status != "PASS":
            # Starting the updates engine is a prerequisite for this write. Do
            # not send a test message when the validation path is unavailable.
            return

        async def step_send() -> str:
            state.send_attempted = True
            response = await client.messages.send(
                peer,
                initial_text,
                silent=True,
                timeout=rpc_timeout,
            )
            message_id = extract_sent_message_id(response, expected_text=initial_text)
            if message_id is None:
                observed = await _locate_exact_message(
                    client=client,
                    peer=peer,
                    token=token,
                    expected_text=initial_text,
                    expected_id=None,
                    timeout=rpc_timeout,
                )
                identity = message_id_and_text(observed)
                if identity is None:
                    raise AssertionError("Observed send result did not contain a safe message ID")
                message_id = identity[0]
            state.message_id = message_id
            resource_ids["message_id"] = message_id
            return f"sent exact test message id={message_id} token={token}"

        await run_step(
            name="messages.destructive.send",
            fn=step_send,
            client=client,
            reporter=reporter,
            results=results,
        )

        async def step_observe_update() -> str:
            observed = await _observe_exact_message_update(
                client=client,
                expected_text=initial_text,
                expected_id=state.message_id,
                timeout=update_timeout,
            )
            if state.message_id is None:
                state.message_id = observed.message_id
                resource_ids["message_id"] = observed.message_id
            await _assert_update_stream_healthy(client)
            resource_ids["observed_update_kind"] = observed.update_kind
            return (
                f"observed exact test-message update id={observed.message_id} "
                f"kind={observed.update_kind} inspected={observed.inspected_updates}"
            )

        await run_step(
            name="updates.destructive.observe_send",
            fn=step_observe_update,
            client=client,
            reporter=reporter,
            results=results,
        )

        async def step_verify_send() -> str:
            if state.message_id is None:
                raise AssertionError("Send step did not produce a message ID")
            await _locate_exact_message(
                client=client,
                peer=peer,
                token=token,
                expected_text=initial_text,
                expected_id=state.message_id,
                timeout=rpc_timeout,
            )
            return f"verified initial text id={state.message_id}"

        await run_step(
            name="messages.destructive.verify_send",
            fn=step_verify_send,
            client=client,
            reporter=reporter,
            results=results,
        )

        async def step_edit() -> str:
            if state.message_id is None:
                raise AssertionError("Send step did not produce a message ID")
            await client.messages.edit(
                peer,
                state.message_id,
                edited_text,
                no_webpage=True,
                timeout=rpc_timeout,
            )
            return f"edited exact test message id={state.message_id}"

        await run_step(
            name="messages.destructive.edit",
            fn=step_edit,
            client=client,
            reporter=reporter,
            results=results,
        )

        async def step_verify_edit() -> str:
            if state.message_id is None:
                raise AssertionError("Send step did not produce a message ID")
            await _locate_exact_message(
                client=client,
                peer=peer,
                token=token,
                expected_text=edited_text,
                expected_id=state.message_id,
                timeout=rpc_timeout,
            )
            return f"verified edited text id={state.message_id}"

        await run_step(
            name="messages.destructive.verify_edit",
            fn=step_verify_edit,
            client=client,
            reporter=reporter,
            results=results,
        )
    finally:
        await finalize_run(
            client=client,
            ctx=ctx,
            reporter=reporter,
            results=results,
            resource_ids=resource_ids,
        )


def test_live_destructive_message_roundtrip(
    client_v2: Client,
    live_context: Any,
    audit_reporter: Any,
) -> None:
    if live_context.cfg.live_profile != DESTRUCTIVE_MESSAGE_PROFILE:
        pytest.skip("Destructive round-trip requires the destructive_message profile")
    if not live_context.source_tree_clean:
        raise pytest.UsageError("Destructive live evidence requires a clean source tree")
    peer = live_context.cfg.destructive_peer
    if not isinstance(peer, str) or not peer:
        raise pytest.UsageError("Destructive live peer was not resolved by the authorization gate")

    asyncio.run(
        _run_destructive_message_roundtrip(
            client_v2,
            live_context,
            audit_reporter,
            peer=peer,
        )
    )
