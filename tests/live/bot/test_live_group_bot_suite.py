from __future__ import annotations

import asyncio
import os
import secrets
from typing import Any

import pytest

from telecraft.bot import Dispatcher, Router, and_, command, incoming
from telecraft.client import Client

pytestmark = [pytest.mark.live, pytest.mark.live_optional, pytest.mark.live_bot]


def _decode_message_text(raw: Any) -> str:
    msg = getattr(raw, "message", "")
    if isinstance(msg, bytes):
        return msg.decode("utf-8", "replace")
    if isinstance(msg, str):
        return msg
    return str(msg)


async def _run_bot_ping_roundtrip(
    *,
    user_client: Client,
    bot_client: Client,
    target_peer: str,
    timeout: float,
) -> None:
    nonce = secrets.token_hex(4)
    probe = f"/ping {nonce}"
    expected = f"pong-live {nonce}"

    router = Router()

    @router.on_message(and_(incoming(), command("ping")), stop=True)
    async def _on_ping(event):  # type: ignore[no-untyped-def]
        suffix = (event.command_args or "").strip()
        await event.reply(f"pong-live {suffix}".strip())

    bot_dispatcher = Dispatcher(
        client=bot_client.raw,
        router=router,
        ignore_outgoing=True,
        ignore_before_start=True,
        backlog_policy="ignore",
        backlog_grace_seconds=2,
        debug=False,
    )

    await bot_client.connect(timeout=timeout)
    bot_task = asyncio.create_task(bot_dispatcher.run(), name="live-group-bot-dispatcher")
    try:
        await asyncio.sleep(1.0)
        await user_client.connect(timeout=timeout)
        await user_client.messages.send(target_peer, probe, timeout=timeout)

        found = False
        for _ in range(15):
            await asyncio.sleep(2.0)
            history = await user_client.messages.history(target_peer, limit=25, timeout=timeout)
            for item in history:
                if expected in _decode_message_text(item):
                    found = True
                    break
            if found:
                break
        assert found, f"Did not find bot response {expected!r} in peer {target_peer!r}"
    finally:
        bot_task.cancel()
        await asyncio.gather(bot_task, return_exceptions=True)
        await user_client.close()
        await bot_client.close()


def test_group_bot__ping_roundtrip(
    client_v2: Client,
    bot_client_v2: Client,
    live_config: Any,
) -> None:
    peer = os.environ.get("TELECRAFT_LIVE_BOT_TEST_PEER", "").strip()
    if not peer:
        pytest.skip("Set TELECRAFT_LIVE_BOT_TEST_PEER for live bot lane")

    asyncio.run(
        _run_bot_ping_roundtrip(
            user_client=client_v2,
            bot_client=bot_client_v2,
            target_peer=peer,
            timeout=float(live_config.timeout),
        )
    )
