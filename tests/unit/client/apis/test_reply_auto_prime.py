from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from telecraft.bot.events import MessageEvent
from telecraft.client.entities import EntityCacheError
from telecraft.client.mtproto import ClientInit, MtprotoClient


def test_mtproto_client_send_message_user_primes_and_retries() -> None:
    client = MtprotoClient(network="test", dc_id=2, init=ClientInit(api_id=1, api_hash="x"))
    # Pretend connected.
    client._transport = object()  # type: ignore[attr-defined]
    client._sender = object()  # type: ignore[attr-defined]
    client._state = object()  # type: ignore[attr-defined]

    called: dict[str, int] = {"prime": 0, "send": 0}

    async def prime_entities(
        *, limit: int = 100, folder_id: int | None = None, timeout: float = 20.0
    ) -> None:
        called["prime"] += 1
        # Populate the missing access_hash.
        client.entities.user_access_hash[123] = 999

    async def send_message_peer(
        peer: Any,
        text: str,
        *,
        reply_to_msg_id: int | None = None,
        silent: bool = False,
        reply_markup: Any | None = None,
        timeout: float = 20.0,
    ) -> Any:
        _ = (reply_to_msg_id, silent, reply_markup, timeout)
        called["send"] += 1
        return {"peer": peer, "text": text}

    client.prime_entities = prime_entities  # type: ignore[assignment]
    client.send_message_peer = send_message_peer  # type: ignore[assignment]

    res = asyncio.run(client.send_message_user(123, "hi"))
    assert called["prime"] == 1
    assert called["send"] == 1
    assert isinstance(res, dict)


def test_message_event_reply_primes_once_then_falls_back() -> None:
    """
    Verify framework behavior:
    - first send_message_user fails
    - prime_entities called
    - second send_message_user still fails
    - fallback to send_message_self
    """

    @dataclass
    class DummyClient:
        calls: list[str]

        async def send_message_user(
            self, _user_id: int, _text: str, *, reply_markup: Any | None = None
        ) -> Any:
            _ = reply_markup
            self.calls.append("send_user")
            raise EntityCacheError("Unknown user access_hash for user_id=1")

        async def prime_entities(self, *, limit: int = 100, timeout: float = 20.0) -> None:
            self.calls.append("prime")

        async def send_message_self(self, _text: str, *, reply_markup: Any | None = None) -> Any:
            _ = reply_markup
            self.calls.append("send_self")
            return "ok"

    c = DummyClient(calls=[])
    e = MessageEvent(
        client=c,
        raw=object(),
        user_id=1,
        peer_type="user",
        peer_id=1,
        msg_id=1,
        text="x",
    )
    out = asyncio.run(e.reply("y"))
    assert out == "ok"
    assert c.calls == ["send_user", "prime", "send_user", "send_self"]
