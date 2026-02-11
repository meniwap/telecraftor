from __future__ import annotations

import asyncio
from typing import Any

from telecraft.client import Client


class DummyRaw:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self.is_connected = False

    async def connect(self, *, timeout: float = 30.0) -> None:
        self.calls.append(("connect", (), {"timeout": timeout}))
        self.is_connected = True

    async def close(self) -> None:
        self.calls.append(("close", (), {}))
        self.is_connected = False

    async def send_message(self, peer: Any, text: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("send_message", (peer, text), kwargs))
        return {"ok": True, "peer": peer, "text": text}

    async def resolve_peer(self, ref: Any, *, timeout: float = 20.0) -> Any:
        self.calls.append(("resolve_peer", (ref,), {"timeout": timeout}))
        return {"peer_type": "user", "peer_id": 123}

    async def get_contacts(self, *, timeout: float = 20.0) -> list[Any]:
        self.calls.append(("get_contacts", (), {"timeout": timeout}))
        return []

    async def get_me(self, *, timeout: float = 20.0) -> Any:
        self.calls.append(("get_me", (), {"timeout": timeout}))
        return {"id": 1}

    async def start_updates(self, *, timeout: float = 20.0) -> None:
        self.calls.append(("start_updates", (), {"timeout": timeout}))

    async def stop_updates(self) -> None:
        self.calls.append(("stop_updates", (), {}))

    async def recv_update(self) -> Any:
        self.calls.append(("recv_update", (), {}))
        return {"kind": "update"}


def test_client_v2_surface_and_connect_close() -> None:
    raw = DummyRaw()
    c = Client(raw=raw)
    assert c.raw is raw
    assert c.messages is not None
    assert c.chats is not None
    assert c.admin is not None
    assert c.contacts is not None
    assert c.polls is not None
    assert c.folders is not None
    assert c.games is not None
    assert c.saved is not None
    assert c.stars is not None
    assert c.gifts is not None
    assert c.presence is not None
    assert c.profile is not None
    assert c.peers is not None
    assert c.updates is not None

    asyncio.run(c.connect(timeout=7.0))
    assert c.is_connected is True
    asyncio.run(c.close())
    assert c.is_connected is False
    assert ("connect", (), {"timeout": 7.0}) in raw.calls
    assert ("close", (), {}) in raw.calls


def test_client_v2_api_delegation() -> None:
    raw = DummyRaw()
    c = Client(raw=raw)

    out = asyncio.run(c.messages.send("user:1", "hello", silent=True))
    assert out["ok"] is True
    resolved = asyncio.run(c.peers.resolve("@meniwap"))
    assert resolved["peer_id"] == 123
    contacts = asyncio.run(c.contacts.list())
    assert contacts == []
    me = asyncio.run(c.profile.me())
    assert me["id"] == 1

    asyncio.run(c.updates.start(timeout=3.0))
    upd = asyncio.run(c.updates.recv())
    assert upd["kind"] == "update"
    asyncio.run(c.updates.stop())

    call_names = [x[0] for x in raw.calls]
    assert "send_message" in call_names
    assert "resolve_peer" in call_names
    assert "get_contacts" in call_names
    assert "get_me" in call_names
    assert "start_updates" in call_names
    assert "recv_update" in call_names
    assert "stop_updates" in call_names
