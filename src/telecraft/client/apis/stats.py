from __future__ import annotations

from typing import TYPE_CHECKING, Any

from telecraft.client.apis._utils import resolve_input_channel, resolve_input_peer
from telecraft.client.peers import PeerRef
from telecraft.tl.generated.functions import (
    StatsGetBroadcastStats,
    StatsGetMegagroupStats,
    StatsGetMessagePublicForwards,
    StatsGetMessageStats,
    StatsGetStoryPublicForwards,
    StatsGetStoryStats,
    StatsLoadAsyncGraph,
)

if TYPE_CHECKING:
    from telecraft.client.mtproto import MtprotoClient


class StatsChannelsAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def broadcast(
        self,
        channel: PeerRef,
        *,
        dark: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        flags = 1 if dark else 0
        return await self._raw.invoke_api(
            StatsGetBroadcastStats(
                flags=flags,
                dark=True if dark else None,
                channel=await resolve_input_channel(self._raw, channel, timeout=timeout),
            ),
            timeout=timeout,
        )

    async def megagroup(
        self,
        channel: PeerRef,
        *,
        dark: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        flags = 1 if dark else 0
        return await self._raw.invoke_api(
            StatsGetMegagroupStats(
                flags=flags,
                dark=True if dark else None,
                channel=await resolve_input_channel(self._raw, channel, timeout=timeout),
            ),
            timeout=timeout,
        )

    async def message(
        self,
        channel: PeerRef,
        msg_id: int,
        *,
        dark: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        flags = 1 if dark else 0
        return await self._raw.invoke_api(
            StatsGetMessageStats(
                flags=flags,
                dark=True if dark else None,
                channel=await resolve_input_channel(self._raw, channel, timeout=timeout),
                msg_id=int(msg_id),
            ),
            timeout=timeout,
        )

    async def story(
        self,
        channel: PeerRef,
        story_id: int,
        *,
        dark: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        flags = 1 if dark else 0
        return await self._raw.invoke_api(
            StatsGetStoryStats(
                flags=flags,
                dark=True if dark else None,
                peer=await resolve_input_peer(self._raw, channel, timeout=timeout),
                id=int(story_id),
            ),
            timeout=timeout,
        )

    async def broadcast_dark(self, channel: PeerRef, *, timeout: float = 20.0) -> Any:
        return await self.broadcast(channel, dark=True, timeout=timeout)

    async def megagroup_dark(self, channel: PeerRef, *, timeout: float = 20.0) -> Any:
        return await self.megagroup(channel, dark=True, timeout=timeout)


class StatsGraphAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def fetch(
        self,
        token_or_graph_obj: str | Any,
        *,
        x: int = 0,
        dark: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        token: str
        if isinstance(token_or_graph_obj, str):
            token = token_or_graph_obj
        else:
            token = str(getattr(token_or_graph_obj, "token", ""))
            if not token:
                raise ValueError("token_or_graph_obj must provide token")
        flags = 1 if dark else 0
        if x != 0:
            flags |= 2
        return await self._raw.invoke_api(
            StatsLoadAsyncGraph(
                flags=flags,
                token=token,
                x=int(x) if x != 0 else None,
            ),
            timeout=timeout,
        )

    async def fetch_dark(
        self,
        token_or_graph_obj: str | Any,
        *,
        x: int = 0,
        timeout: float = 20.0,
    ) -> Any:
        return await self.fetch(token_or_graph_obj, x=x, dark=True, timeout=timeout)


class StatsPublicForwardsAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def messages(
        self,
        channel: PeerRef,
        msg_id: int,
        *,
        offset: str = "",
        limit: int = 50,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            StatsGetMessagePublicForwards(
                channel=await resolve_input_channel(self._raw, channel, timeout=timeout),
                msg_id=int(msg_id),
                offset=str(offset),
                limit=int(limit),
            ),
            timeout=timeout,
        )

    async def stories(
        self,
        peer: PeerRef,
        story_id: int,
        *,
        offset: str = "",
        limit: int = 50,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            StatsGetStoryPublicForwards(
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                id=int(story_id),
                offset=str(offset),
                limit=int(limit),
            ),
            timeout=timeout,
        )

    async def messages_first_page(
        self,
        channel: PeerRef,
        msg_id: int,
        *,
        timeout: float = 20.0,
    ) -> Any:
        return await self.messages(channel, msg_id, offset="", limit=50, timeout=timeout)

    async def stories_first_page(
        self,
        peer: PeerRef,
        story_id: int,
        *,
        timeout: float = 20.0,
    ) -> Any:
        return await self.stories(peer, story_id, offset="", limit=50, timeout=timeout)


class StatsAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw
        self.channels = StatsChannelsAPI(raw)
        self.graph = StatsGraphAPI(raw)
        self.public_forwards = StatsPublicForwardsAPI(raw)
