from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from telecraft.client.apis._utils import resolve_input_peer
from telecraft.client.chatlists import ChatlistRef
from telecraft.client.peers import PeerRef
from telecraft.tl.generated.functions import (
    ChatlistsCheckChatlistInvite,
    ChatlistsDeleteExportedInvite,
    ChatlistsEditExportedInvite,
    ChatlistsExportChatlistInvite,
    ChatlistsGetChatlistUpdates,
    ChatlistsGetExportedInvites,
    ChatlistsGetLeaveChatlistSuggestions,
    ChatlistsHideChatlistUpdates,
    ChatlistsJoinChatlistInvite,
    ChatlistsJoinChatlistUpdates,
    ChatlistsLeaveChatlist,
)

if TYPE_CHECKING:
    from telecraft.client.mtproto import MtprotoClient


def _chatlist_input(chatlist: ChatlistRef | Any) -> Any:
    if isinstance(chatlist, ChatlistRef):
        return chatlist.to_input()
    return chatlist


async def _input_peers(raw: MtprotoClient, peers: Sequence[PeerRef], *, timeout: float) -> list[Any]:
    return [await resolve_input_peer(raw, peer, timeout=timeout) for peer in peers]


class ChatlistInvitesAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def export(
        self,
        chatlist: ChatlistRef | Any,
        title: str,
        peers: Sequence[PeerRef],
        *,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            ChatlistsExportChatlistInvite(
                chatlist=_chatlist_input(chatlist),
                title=str(title),
                peers=await _input_peers(self._raw, peers, timeout=timeout),
            ),
            timeout=timeout,
        )

    async def list(self, chatlist: ChatlistRef | Any, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            ChatlistsGetExportedInvites(chatlist=_chatlist_input(chatlist)),
            timeout=timeout,
        )

    async def edit(
        self,
        chatlist: ChatlistRef | Any,
        slug: str,
        *,
        title: str | None = None,
        peers: Sequence[PeerRef] | None = None,
        timeout: float = 20.0,
    ) -> Any:
        flags = 0
        input_peers = None
        if title is not None:
            flags |= 2
        if peers is not None:
            flags |= 4
            input_peers = await _input_peers(self._raw, peers, timeout=timeout)
        return await self._raw.invoke_api(
            ChatlistsEditExportedInvite(
                flags=flags,
                chatlist=_chatlist_input(chatlist),
                slug=str(slug),
                title=title,
                peers=input_peers,
            ),
            timeout=timeout,
        )

    async def delete(self, chatlist: ChatlistRef | Any, slug: str, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            ChatlistsDeleteExportedInvite(chatlist=_chatlist_input(chatlist), slug=str(slug)),
            timeout=timeout,
        )

    async def check(self, slug: str, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(ChatlistsCheckChatlistInvite(slug=str(slug)), timeout=timeout)

    async def join(self, slug: str, peers: Sequence[PeerRef], *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            ChatlistsJoinChatlistInvite(
                slug=str(slug),
                peers=await _input_peers(self._raw, peers, timeout=timeout),
            ),
            timeout=timeout,
        )


class ChatlistUpdatesAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def get(self, chatlist: ChatlistRef | Any, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            ChatlistsGetChatlistUpdates(chatlist=_chatlist_input(chatlist)),
            timeout=timeout,
        )

    async def join(
        self,
        chatlist: ChatlistRef | Any,
        peers: Sequence[PeerRef],
        *,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            ChatlistsJoinChatlistUpdates(
                chatlist=_chatlist_input(chatlist),
                peers=await _input_peers(self._raw, peers, timeout=timeout),
            ),
            timeout=timeout,
        )

    async def hide(self, chatlist: ChatlistRef | Any, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            ChatlistsHideChatlistUpdates(chatlist=_chatlist_input(chatlist)),
            timeout=timeout,
        )


class ChatlistSuggestionsAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def leave(self, chatlist: ChatlistRef | Any, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            ChatlistsGetLeaveChatlistSuggestions(chatlist=_chatlist_input(chatlist)),
            timeout=timeout,
        )


class ChatlistsAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw
        self.invites = ChatlistInvitesAPI(raw)
        self.updates = ChatlistUpdatesAPI(raw)
        self.suggestions = ChatlistSuggestionsAPI(raw)

    async def leave(
        self,
        chatlist: ChatlistRef | Any,
        peers: Sequence[PeerRef],
        *,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            ChatlistsLeaveChatlist(
                chatlist=_chatlist_input(chatlist),
                peers=await _input_peers(self._raw, peers, timeout=timeout),
            ),
            timeout=timeout,
        )
