from __future__ import annotations

import asyncio
from typing import Any

import pytest

from telecraft.client import Client
from telecraft.mtproto.rpc.sender import (
    MtprotoEncryptedSender,
    ReceivedMessage,
    UpdatesRecoveryRequired,
)
from telecraft.tl.generated.types import UpdateConfig

pytestmark = [
    pytest.mark.live,
    pytest.mark.live_prod_safe,
    pytest.mark.live_recovery_fault,
]

_SYNTHETIC_CONSTRUCTOR_ID = 0x7F00C0DE
_LAYER_BOOTSTRAP = "layer_bootstrap"
_GET_DIFFERENCE = "updates.getDifference"


def _successful_recovery_call_kind(request: object) -> str | None:
    if str(getattr(request, "TL_NAME", "")) == _GET_DIFFERENCE:
        return _GET_DIFFERENCE
    if str(getattr(request, "TL_NAME", "")) != "invokeWithLayer":
        return None
    init = getattr(request, "query", None)
    if str(getattr(init, "TL_NAME", "")) != "initConnection":
        return None
    query = getattr(init, "query", None)
    if str(getattr(query, "TL_NAME", "")) != "help.getConfig":
        return None
    return _LAYER_BOOTSTRAP


async def _wait_for_replacement(
    raw: Any,
    *,
    old_sender: object,
    old_transport: object,
    old_incoming: object,
) -> None:
    while True:
        terminal = raw._updates_terminal
        if terminal is not None and terminal.done():
            raise terminal.result()
        if (
            raw._sender is not None
            and raw._sender is not old_sender
            and raw._transport is not None
            and raw._transport is not old_transport
            and raw._incoming is not None
            and raw._incoming is not old_incoming
            and raw._did_init_connection is True
            and raw._migration_in_progress is False
        ):
            return
        await asyncio.sleep(0.05)


async def _wait_for_sentinel(client: Client, sentinel: object) -> None:
    for _ in range(8192):
        update = await client.updates.recv()
        if update is sentinel:
            return
    raise AssertionError("Replacement update stream did not deliver its health sentinel")


async def _run_recovery_smoke(
    client: Client,
    *,
    timeout: float,
    successful_calls: dict[int, set[str]],
) -> None:
    try:
        await asyncio.wait_for(client.connect(timeout=timeout), timeout=timeout)
        await asyncio.wait_for(client.updates.start(timeout=timeout), timeout=timeout)
        raw = client.raw
        old_sender = raw._sender
        old_transport = raw._transport
        old_state = raw._state
        old_incoming = raw._incoming
        if old_sender is None or old_transport is None or old_state is None or old_incoming is None:
            raise AssertionError("Connected update client did not expose complete MTProto state")

        old_auth_key = bytes(old_state.auth_key)
        old_session_id = bytes(old_state.session_id)

        await old_incoming.put(
            UpdatesRecoveryRequired(
                reason="live_synthetic_unknown_constructor",
                requires_reconnect=True,
                constructor_id=_SYNTHETIC_CONSTRUCTOR_ID,
                expected_type="Message",
                path="live.synthetic.Message",
                position=0,
            )
        )

        async def validate_recovery() -> None:
            await _wait_for_replacement(
                raw,
                old_sender=old_sender,
                old_transport=old_transport,
                old_incoming=old_incoming,
            )

            new_sender = raw._sender
            new_transport = raw._transport
            new_state = raw._state
            new_incoming = raw._incoming
            if (
                new_sender is None
                or new_transport is None
                or new_state is None
                or new_incoming is None
            ):
                raise AssertionError("Recovery published incomplete replacement state")

            assert new_sender is not old_sender
            assert new_transport is not old_transport
            assert new_incoming is not old_incoming
            assert len(new_state.session_id) == 8
            assert bytes(new_state.session_id) != old_session_id
            assert bytes(new_state.auth_key) == old_auth_key
            # Telegram may legitimately rotate the salt during reconnect.
            assert len(new_state.server_salt) == 8
            assert raw._did_init_connection is True
            assert raw.config is not None
            assert old_sender.is_healthy is False
            assert new_sender.is_healthy is True

            # The recovery signal is processed serially: this sentinel can reach
            # the output queue only after fresh-connection layer initialization
            # and the automatic real updates.getDifference call both complete.
            sentinel = UpdateConfig()
            await new_incoming.put(ReceivedMessage(msg_id=0, seqno=0, obj=sentinel))
            await _wait_for_sentinel(client, sentinel)
            replacement_calls = successful_calls.get(id(new_sender), set())
            assert _LAYER_BOOTSTRAP in replacement_calls
            assert _GET_DIFFERENCE in replacement_calls

            updates_task = raw._updates_task
            terminal = raw._updates_terminal
            assert updates_task is not None and not updates_task.done()
            assert terminal is not None and not terminal.done()
            # updateConfig proves delivery and drives a real config RPC, but it
            # carries no pts/qts/seq/channel_pts progress. It must not disarm the
            # poison circuit before an independently healthy cursor-bearing live
            # update is decoded, delivered, and persisted.
            assert raw._unknown_constructor_fingerprint == (
                _SYNTHETIC_CONSTRUCTOR_ID,
                "live.synthetic.Message",
            )
            assert raw._unknown_constructor_repeat_count == 1
            assert raw._unknown_constructor_consecutive_failure_count == 1
            assert raw._unknown_constructor_reconnect_attempt_count == 1
            assert client.is_connected

            # Final live RPC proves the adopted sender remains usable after the
            # update loop's own post-recovery config request.
            me = await client.profile.me(timeout=timeout)
            assert isinstance(getattr(me, "id", None), int)

        await asyncio.wait_for(validate_recovery(), timeout=timeout)
    finally:
        await asyncio.wait_for(client.close(), timeout=min(timeout, 10.0))


def test_live_unknown_constructor_recovery__replaces_connection_and_resumes_updates(
    client_v2: Client,
    live_config: Any,
    live_source_snapshot: tuple[str, bool],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _source_commit, source_tree_clean = live_source_snapshot
    if not source_tree_clean:
        raise pytest.UsageError("Live recovery smoke requires a clean source tree")
    successful_calls: dict[int, set[str]] = {}
    original_invoke_tl = MtprotoEncryptedSender.invoke_tl

    async def recording_invoke_tl(
        sender: MtprotoEncryptedSender,
        request: Any,
        **kwargs: Any,
    ) -> Any:
        result = await original_invoke_tl(sender, request, **kwargs)
        call_kind = _successful_recovery_call_kind(request)
        if call_kind is not None:
            successful_calls.setdefault(id(sender), set()).add(call_kind)
        return result

    # Observation only: the real request, decoder, transport, and result are untouched.
    monkeypatch.setattr(MtprotoEncryptedSender, "invoke_tl", recording_invoke_tl)
    timeout = min(float(live_config.timeout), 30.0)
    asyncio.run(
        _run_recovery_smoke(
            client_v2,
            timeout=timeout,
            successful_calls=successful_calls,
        )
    )
