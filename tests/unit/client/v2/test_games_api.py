from __future__ import annotations

import asyncio
from typing import Any

from telecraft.client import Client


class _RawGames:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    async def roll_dice(
        self,
        peer: Any,
        *,
        reply_to_msg_id: int | None = None,
        silent: bool = False,
        timeout: float = 20.0,
    ) -> dict[str, Any]:
        self.calls.append(
            (
                "roll_dice",
                (peer,),
                {
                    "reply_to_msg_id": reply_to_msg_id,
                    "silent": silent,
                    "timeout": timeout,
                },
            )
        )
        return {"ok": True}


def test_games__roll_dice__delegates_to_raw() -> None:
    raw = _RawGames()
    client = Client(raw=raw)
    out = asyncio.run(client.games.roll_dice("user:1", timeout=7.0))
    assert out["ok"] is True
    assert raw.calls == [
        (
            "roll_dice",
            ("user:1",),
            {"reply_to_msg_id": None, "silent": False, "timeout": 7.0},
        )
    ]
