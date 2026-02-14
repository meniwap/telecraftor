from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from telecraft.client.apis._utils import resolve_input_peer, resolve_input_user
from telecraft.client.peers import PeerRef
from telecraft.client.premium import PremiumBoostSlots, build_premium_slots
from telecraft.tl.generated.functions import (
    PremiumApplyBoost,
    PremiumGetBoostsList,
    PremiumGetBoostsStatus,
    PremiumGetMyBoosts,
    PremiumGetUserBoosts,
)

if TYPE_CHECKING:
    from telecraft.client.mtproto import MtprotoClient


class PremiumBoostsAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def list(
        self,
        peer: PeerRef,
        *,
        gifts: bool = False,
        offset: str = "",
        limit: int = 100,
        timeout: float = 20.0,
    ) -> Any:
        flags = 1 if gifts else 0
        return await self._raw.invoke_api(
            PremiumGetBoostsList(
                flags=flags,
                gifts=True if gifts else None,
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                offset=str(offset),
                limit=int(limit),
            ),
            timeout=timeout,
        )

    async def my(self, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(PremiumGetMyBoosts(), timeout=timeout)

    async def apply(
        self,
        peer: PeerRef,
        *,
        slots: PremiumBoostSlots | Sequence[int] | None = None,
        timeout: float = 20.0,
    ) -> Any:
        flags = 1 if slots is not None else 0
        return await self._raw.invoke_api(
            PremiumApplyBoost(
                flags=flags,
                slots=build_premium_slots(slots),
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
            ),
            timeout=timeout,
        )

    async def status(self, peer: PeerRef, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            PremiumGetBoostsStatus(
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
            ),
            timeout=timeout,
        )

    async def user(self, peer: PeerRef, user: PeerRef, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            PremiumGetUserBoosts(
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                user_id=await resolve_input_user(self._raw, user, timeout=timeout),
            ),
            timeout=timeout,
        )


class PremiumAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw
        self.boosts = PremiumBoostsAPI(raw)
