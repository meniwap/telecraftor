from __future__ import annotations

import asyncio
from typing import Any

from telecraft.client import Client


class _Entities:
    def input_channel(self, peer_id: int) -> dict[str, int]:
        return {"input_channel": int(peer_id)}


class _RawChannels:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self.entities = _Entities()

    async def resolve_peer(self, ref: Any, *, timeout: float = 20.0) -> Any:
        self.calls.append(("resolve_peer", (ref,), {"timeout": timeout}))
        return type("Peer", (), {"peer_type": "channel", "peer_id": 1})()

    async def invoke_api(self, req: Any, *, timeout: float = 20.0) -> dict[str, Any]:
        self.calls.append(("invoke_api", (req,), {"timeout": timeout}))
        return {"ok": True, "request": type(req).__name__}


def test_channels__read_history__delegates_to_raw() -> None:
    raw = _RawChannels()
    client = Client(raw=raw)
    out = asyncio.run(client.channels.read_history("channel:1", timeout=5.0))
    assert out["ok"] is True
    assert any(name == "invoke_api" for name, _, _ in raw.calls)

