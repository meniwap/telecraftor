from __future__ import annotations

from typing import TYPE_CHECKING, Any

from telecraft.client.apis._utils import resolve_input_peer_or_self
from telecraft.client.peers import PeerRef
from telecraft.tl.generated.functions import (
    BotsGetBotRecommendations,
    BotsGetPopularAppBots,
    ChannelsGetChannelRecommendations,
    ChannelsGetGroupsForDiscussion,
    ChannelsGetLeftChannels,
    ContactsGetSponsoredPeers,
    MessagesGetPeerSettings,
)
from telecraft.tl.generated.types import InputPeerEmpty, InputUserSelf

if TYPE_CHECKING:
    from telecraft.client.mtproto import MtprotoClient


class DiscoveryChannelsAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def recommended(self, peer: PeerRef | str | None = None, *, timeout: float = 20.0) -> Any:
        if peer is None:
            return await self._raw.invoke_api(
                ChannelsGetChannelRecommendations(flags=0, channel=None),
                timeout=timeout,
            )
        return await self._raw.invoke_api(
            ChannelsGetChannelRecommendations(
                flags=1,
                channel=await resolve_input_peer_or_self(self._raw, peer, timeout=timeout),
            ),
            timeout=timeout,
        )

    async def for_peer(self, peer: PeerRef | str, *, timeout: float = 20.0) -> Any:
        return await self.recommended(peer=peer, timeout=timeout)

    async def left(self, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(ChannelsGetLeftChannels(offset=0), timeout=timeout)

    async def groups_for_discussion(self, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(ChannelsGetGroupsForDiscussion(), timeout=timeout)


class DiscoveryBotsAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def recommended(self, peer: PeerRef | str | None = None, *, timeout: float = 20.0) -> Any:
        bot = InputUserSelf()
        if peer is not None:
            bot = await resolve_input_peer_or_self(self._raw, peer, timeout=timeout)
        return await self._raw.invoke_api(BotsGetBotRecommendations(bot=bot), timeout=timeout)

    async def for_peer(self, peer: PeerRef | str, *, timeout: float = 20.0) -> Any:
        return await self.recommended(peer=peer, timeout=timeout)

    async def popular_apps(
        self,
        *,
        offset: str = "",
        limit: int = 20,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            BotsGetPopularAppBots(offset=str(offset), limit=int(limit)),
            timeout=timeout,
        )


class DiscoverySponsoredAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def peers(self, q: str = "", *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            ContactsGetSponsoredPeers(q=str(q)),
            timeout=timeout,
        )


class DiscoveryAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw
        self.channels = DiscoveryChannelsAPI(raw)
        self.bots = DiscoveryBotsAPI(raw)
        self.sponsored = DiscoverySponsoredAPI(raw)

    async def peer_settings(self, peer: PeerRef, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            MessagesGetPeerSettings(
                peer=await resolve_input_peer_or_self(self._raw, peer, timeout=timeout)
            ),
            timeout=timeout,
        )

    async def recent_peers(self, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            MessagesGetPeerSettings(peer=InputPeerEmpty()),
            timeout=timeout,
        )

    async def bot_profile_settings(self, peer: PeerRef, *, timeout: float = 20.0) -> Any:
        return await self.peer_settings(peer, timeout=timeout)
