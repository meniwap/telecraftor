from __future__ import annotations

import asyncio
from typing import Any

from telecraft.client.mtproto import ClientInit, MtprotoClient


def _make_connected_client() -> MtprotoClient:
    c = MtprotoClient(network="test", dc_id=2, init=ClientInit(api_id=1, api_hash="x"))
    c._transport = object()  # type: ignore[attr-defined]
    c._sender = object()  # type: ignore[attr-defined]
    c._state = object()  # type: ignore[attr-defined]
    return c


def test_add_user_to_basic_chat_uses_messages_add_chat_user() -> None:
    c = _make_connected_client()
    c.entities.user_access_hash[200] = 777

    seen: list[Any] = []

    async def invoke_api(req: Any, *, timeout: float = 0) -> Any:
        seen.append(req)
        return type("_R", (), {"users": [], "chats": []})()

    c.invoke_api = invoke_api  # type: ignore[assignment]

    asyncio.run(c.add_user_to_group(("chat", 100), ("user", 200), fwd_limit=5))
    assert len(seen) == 1
    req = seen[0]
    assert getattr(req, "TL_NAME", None) == "messages.addChatUser"
    assert req.chat_id == 100
    assert getattr(getattr(req, "user_id", None), "TL_NAME", None) == "inputUser"
    assert req.fwd_limit == 5


def test_add_user_to_channel_uses_channels_invite_to_channel() -> None:
    c = _make_connected_client()
    c.entities.user_access_hash[200] = 777
    c.entities.channel_access_hash[300] = 999

    seen: list[Any] = []

    async def invoke_api(req: Any, *, timeout: float = 0) -> Any:
        seen.append(req)
        return type("_R", (), {"users": [], "chats": []})()

    c.invoke_api = invoke_api  # type: ignore[assignment]

    asyncio.run(c.add_user_to_group(("channel", 300), ("user", 200)))
    assert len(seen) == 1
    req = seen[0]
    assert getattr(req, "TL_NAME", None) == "channels.inviteToChannel"
    assert getattr(getattr(req, "channel", None), "TL_NAME", None) == "inputChannel"
    users = getattr(req, "users", None)
    assert isinstance(users, list) and len(users) == 1
    assert getattr(users[0], "TL_NAME", None) == "inputUser"
