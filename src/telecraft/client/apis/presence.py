from __future__ import annotations

from typing import TYPE_CHECKING, Any

from telecraft.client.peers import PeerRef

if TYPE_CHECKING:
    from telecraft.client.mtproto import MtprotoClient


class PresenceAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def ping(self, *, timeout: float = 20.0) -> Any:
        return await self._raw.ping(timeout=timeout)

    async def action(self, peer: PeerRef, action: str = "typing", *, timeout: float = 20.0) -> Any:
        return await self._raw.send_action(peer, action, timeout=timeout)
