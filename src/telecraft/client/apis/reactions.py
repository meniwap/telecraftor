from __future__ import annotations

from typing import TYPE_CHECKING, Any

from telecraft.client.apis._utils import resolve_input_peer
from telecraft.client.peers import PeerRef
from telecraft.tl.generated.functions import (
    MessagesClearRecentReactions,
    MessagesGetAvailableReactions,
    MessagesGetMessageReactionsList,
    MessagesGetMessagesReactions,
    MessagesGetTopReactions,
    MessagesGetUnreadReactions,
)

if TYPE_CHECKING:
    from telecraft.client.mtproto import MtprotoClient


class ReactionsAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def available(self, *, hash: int = 0, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            MessagesGetAvailableReactions(hash=int(hash)),
            timeout=timeout,
        )

    async def top(self, *, limit: int = 100, hash: int = 0, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            MessagesGetTopReactions(limit=int(limit), hash=int(hash)),
            timeout=timeout,
        )

    async def unread(
        self,
        peer: PeerRef,
        *,
        offset_id: int = 0,
        add_offset: int = 0,
        limit: int = 100,
        max_id: int = 0,
        min_id: int = 0,
        top_msg_id: int | None = None,
        saved_peer_id: PeerRef | None = None,
        timeout: float = 20.0,
    ) -> Any:
        flags = 0
        saved_input = None
        if top_msg_id is not None:
            flags |= 1
        if saved_peer_id is not None:
            flags |= 2
            saved_input = await resolve_input_peer(self._raw, saved_peer_id, timeout=timeout)
        return await self._raw.invoke_api(
            MessagesGetUnreadReactions(
                flags=flags,
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                top_msg_id=int(top_msg_id) if top_msg_id is not None else None,
                saved_peer_id=saved_input,
                offset_id=int(offset_id),
                add_offset=int(add_offset),
                limit=int(limit),
                max_id=int(max_id),
                min_id=int(min_id),
            ),
            timeout=timeout,
        )

    async def by_messages(
        self,
        peer: PeerRef,
        msg_ids: int | list[int],
        *,
        timeout: float = 20.0,
    ) -> Any:
        if isinstance(msg_ids, int):
            ids = [msg_ids]
        else:
            ids = [int(x) for x in msg_ids]
        return await self._raw.invoke_api(
            MessagesGetMessagesReactions(
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                id=ids,
            ),
            timeout=timeout,
        )

    async def list_for_message(
        self,
        peer: PeerRef,
        msg_id: int,
        *,
        reaction: Any | None = None,
        offset: str = "",
        limit: int = 100,
        timeout: float = 20.0,
    ) -> Any:
        flags = 0
        reaction_obj = None
        offset_value = None
        if reaction is not None:
            flags |= 1
            reaction_obj = reaction
        if offset:
            flags |= 2
            offset_value = str(offset)
        return await self._raw.invoke_api(
            MessagesGetMessageReactionsList(
                flags=flags,
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                id=int(msg_id),
                reaction=reaction_obj,
                offset=offset_value,
                limit=int(limit),
            ),
            timeout=timeout,
        )

    async def clear_recent(self, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(MessagesClearRecentReactions(), timeout=timeout)
