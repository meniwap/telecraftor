from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

from telecraft.client.mtproto import ClientInit, MtprotoClient
from telecraft.client.peers import Peer
from telecraft.tl.generated.types import InputPeerChannel, MessagesChannelMessages


def test_get_history_returns_messages_from_channel_response() -> None:
    client = MtprotoClient(
        network="test",
        dc_id=2,
        init=ClientInit(api_id=1, api_hash="x"),
    )
    client.entities.channel_access_hash[123] = 456

    first = SimpleNamespace(TL_NAME="message", id=20, message="newer")
    second = SimpleNamespace(TL_NAME="message", id=19, message="older")
    channel = SimpleNamespace(
        TL_NAME="channel",
        id=123,
        access_hash=456,
        username="history_group",
    )
    user = SimpleNamespace(
        TL_NAME="user",
        id=42,
        access_hash=789,
        username="history_author",
    )
    response = MessagesChannelMessages(
        flags=0,
        inexact=False,
        pts=10,
        count=2,
        offset_id_offset=None,
        messages=[first, second],
        topics=[],
        chats=[channel],
        users=[user],
    )

    async def invoke_api(request: Any, *, timeout: float = 0) -> Any:
        assert request.TL_NAME == "messages.getHistory"
        assert isinstance(request.peer, InputPeerChannel)
        assert request.limit == 2
        assert timeout == 7.5
        return response

    client.invoke_api = invoke_api  # type: ignore[assignment]

    result = asyncio.run(client.get_history(Peer.channel(123), limit=2, timeout=7.5))

    assert result == [first, second]
    assert client.entities.user_access_hash[42] == 789
    assert client.entities.username_to_peer["history_group"] == ("channel", 123)
