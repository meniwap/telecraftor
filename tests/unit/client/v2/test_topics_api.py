from __future__ import annotations

import asyncio
from typing import Any

from telecraft.client import Client


class _Entities:
    def input_peer(self, resolved: Any) -> dict[str, Any]:
        return {"input_peer": resolved}


class _RawTopics:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self.entities = _Entities()

    async def resolve_peer(self, ref: Any, *, timeout: float = 20.0) -> Any:
        self.calls.append(("resolve_peer", (ref,), {"timeout": timeout}))
        return type("Peer", (), {"peer_type": "channel", "peer_id": 1})()

    async def invoke_api(self, req: Any, *, timeout: float = 20.0) -> dict[str, Any]:
        self.calls.append(("invoke_api", (req,), {"timeout": timeout}))
        return {"ok": True, "request": type(req).__name__}


def test_topics__list__delegates_to_raw() -> None:
    raw = _RawTopics()
    client = Client(raw=raw)
    out = asyncio.run(client.topics.list("channel:1", limit=5, timeout=7.0))
    assert out["ok"] is True
    assert any(name == "invoke_api" for name, _, _ in raw.calls)
