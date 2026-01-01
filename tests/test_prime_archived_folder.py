from __future__ import annotations

import asyncio
from typing import Any

from telecraft.client.entities import EntityCacheError
from telecraft.client.mtproto import ClientInit, MtprotoClient


def test_send_message_channel_primes_archived_folder_when_needed() -> None:
    """
    Repro for: commands work in Saved Messages but not in a (possibly archived) supergroup.

    We simulate:
    - first priming (folder_id=None) does NOT populate channel_access_hash
    - archived priming (folder_id=1) DOES populate it
    - send_message_channel then succeeds (calls send_message_peer once)
    """
    c = MtprotoClient(network="test", dc_id=2, init=ClientInit(api_id=1, api_hash="x"))
    c._transport = object()  # type: ignore[attr-defined]
    c._sender = object()  # type: ignore[attr-defined]
    c._state = object()  # type: ignore[attr-defined]

    calls: list[tuple[str, int | None]] = []

    async def prime_entities(*, limit: int = 100, folder_id: int | None = None, timeout: float = 20.0) -> None:
        calls.append(("prime", folder_id))
        # Only archived folder contains our channel.
        if folder_id == 1:
            c.entities.channel_access_hash[123] = 999

    async def send_message_peer(_peer: Any, _text: str, *, timeout: float = 20.0) -> Any:
        calls.append(("send", None))
        return "ok"

    c.prime_entities = prime_entities  # type: ignore[assignment]
    c.send_message_peer = send_message_peer  # type: ignore[assignment]

    out = asyncio.run(c.send_message_channel(123, "hi"))
    assert out == "ok"
    assert ("prime", None) in calls
    assert ("prime", 1) in calls
    assert ("send", None) in calls


