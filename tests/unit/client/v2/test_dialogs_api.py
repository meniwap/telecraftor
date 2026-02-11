from __future__ import annotations

import asyncio
from typing import Any

from telecraft.client import Client


class _RawDialogs:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    async def invoke_api(self, req: Any, *, timeout: float = 20.0) -> dict[str, Any]:
        self.calls.append(("invoke_api", (req,), {"timeout": timeout}))
        return {"ok": True, "request": type(req).__name__}


def test_dialogs__list__delegates_to_raw() -> None:
    raw = _RawDialogs()
    client = Client(raw=raw)
    out = asyncio.run(client.dialogs.list(limit=5, timeout=6.0))
    assert out["ok"] is True
    assert len(raw.calls) == 1
    assert raw.calls[0][0] == "invoke_api"
    assert raw.calls[0][2]["timeout"] == 6.0
