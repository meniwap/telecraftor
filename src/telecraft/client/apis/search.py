from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from telecraft.client.apis._utils import resolve_input_peer, resolve_input_peer_or_self
from telecraft.client.peers import PeerRef
from telecraft.tl.generated.functions import (
    ChannelsSearchPosts,
    MessagesGetReplies,
    MessagesGetSearchCounters,
    MessagesGetSearchResultsCalendar,
    MessagesGetSearchResultsPositions,
    MessagesSearchGlobal,
)
from telecraft.tl.generated.types import InputMessagesFilterEmpty, InputPeerEmpty

if TYPE_CHECKING:
    from telecraft.client.mtproto import MtprotoClient


class SearchAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def global_messages(
        self,
        *,
        q: str = "",
        filter: Any | None = None,
        offset_rate: int = 0,
        offset_peer: PeerRef | str | None = None,
        offset_id: int = 0,
        limit: int = 100,
        min_date: int = 0,
        max_date: int = 0,
        broadcasts_only: bool = False,
        groups_only: bool = False,
        users_only: bool = False,
        folder_id: int | None = None,
        timeout: float = 20.0,
    ) -> Any:
        flags = 0
        if broadcasts_only:
            flags |= 1
        if groups_only:
            flags |= 2
        if users_only:
            flags |= 4
        if folder_id is not None:
            flags |= 8

        if offset_peer is None:
            input_offset_peer: Any = InputPeerEmpty()
        else:
            input_offset_peer = await resolve_input_peer_or_self(
                self._raw,
                offset_peer,
                timeout=timeout,
            )

        return await self._raw.invoke_api(
            MessagesSearchGlobal(
                flags=flags,
                broadcasts_only=True if broadcasts_only else None,
                groups_only=True if groups_only else None,
                users_only=True if users_only else None,
                folder_id=int(folder_id) if folder_id is not None else None,
                q=str(q),
                filter=filter if filter is not None else InputMessagesFilterEmpty(),
                min_date=int(min_date),
                max_date=int(max_date),
                offset_rate=int(offset_rate),
                offset_peer=input_offset_peer,
                offset_id=int(offset_id),
                limit=int(limit),
            ),
            timeout=timeout,
        )

    async def public_posts(
        self,
        peer: PeerRef | str | None = None,
        *,
        q: str = "",
        hashtag: str | None = None,
        offset: str = "",
        limit: int = 50,
        allow_paid_stars: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        flags = 0
        if hashtag:
            flags |= 1
        if allow_paid_stars:
            flags |= 2

        offset_peer: Any
        if peer is None:
            offset_peer = InputPeerEmpty()
        else:
            offset_peer = await resolve_input_peer_or_self(self._raw, peer, timeout=timeout)

        return await self._raw.invoke_api(
            ChannelsSearchPosts(
                flags=flags,
                hashtag=str(hashtag) if hashtag else None,
                query=str(q),
                offset_rate=0,
                offset_peer=offset_peer,
                offset_id=int(offset) if str(offset).isdigit() else 0,
                limit=int(limit),
                allow_paid_stars=True if allow_paid_stars else None,
            ),
            timeout=timeout,
        )

    async def sent_media(
        self,
        peer: PeerRef,
        *,
        q: str = "",
        filter: Any | None = None,
        offset_id: int = 0,
        limit: int = 100,
        timeout: float = 20.0,
    ) -> list[Any]:
        # searchSentMedia is global; for dialog-targeted UX we reuse search_messages.
        _ = filter
        return await self._raw.search_messages(
            peer,
            query=str(q),
            offset_id=int(offset_id),
            limit=int(limit),
            timeout=timeout,
        )

    async def calendar(
        self,
        peer: PeerRef,
        *,
        filter: Any | None = None,
        offset_id: int = 0,
        offset_date: int = 0,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            MessagesGetSearchResultsCalendar(
                flags=0,
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                saved_peer_id=None,
                filter=filter if filter is not None else InputMessagesFilterEmpty(),
                offset_id=int(offset_id),
                offset_date=int(offset_date),
            ),
            timeout=timeout,
        )

    async def counters(
        self,
        peer: PeerRef,
        *,
        filters: Sequence[Any] = (),
        timeout: float = 20.0,
    ) -> Any:
        payload_filters = list(filters) if filters else [InputMessagesFilterEmpty()]
        return await self._raw.invoke_api(
            MessagesGetSearchCounters(
                flags=0,
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                saved_peer_id=None,
                top_msg_id=None,
                filters=payload_filters,
            ),
            timeout=timeout,
        )

    async def positions(
        self,
        peer: PeerRef,
        *,
        filter: Any | None = None,
        offset_id: int = 0,
        limit: int = 100,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            MessagesGetSearchResultsPositions(
                flags=0,
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                saved_peer_id=None,
                filter=filter if filter is not None else InputMessagesFilterEmpty(),
                offset_id=int(offset_id),
                limit=int(limit),
            ),
            timeout=timeout,
        )

    async def discussion_replies(
        self,
        peer: PeerRef,
        msg_id: int,
        *,
        offset_id: int = 0,
        add_offset: int = 0,
        limit: int = 100,
        max_id: int = 0,
        min_id: int = 0,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            MessagesGetReplies(
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                msg_id=int(msg_id),
                offset_id=int(offset_id),
                offset_date=0,
                add_offset=int(add_offset),
                limit=int(limit),
                max_id=int(max_id),
                min_id=int(min_id),
                hash=0,
            ),
            timeout=timeout,
        )

    async def global_broadcasts(
        self,
        *,
        q: str = "",
        limit: int = 100,
        timeout: float = 20.0,
    ) -> Any:
        return await self.global_messages(
            q=q,
            broadcasts_only=True,
            limit=limit,
            timeout=timeout,
        )

    async def global_groups(
        self,
        *,
        q: str = "",
        limit: int = 100,
        timeout: float = 20.0,
    ) -> Any:
        return await self.global_messages(
            q=q,
            groups_only=True,
            limit=limit,
            timeout=timeout,
        )

    async def global_users(
        self,
        *,
        q: str = "",
        limit: int = 100,
        timeout: float = 20.0,
    ) -> Any:
        return await self.global_messages(
            q=q,
            users_only=True,
            limit=limit,
            timeout=timeout,
        )

    async def global_in_folder(
        self,
        folder_id: int,
        *,
        q: str = "",
        limit: int = 100,
        timeout: float = 20.0,
    ) -> Any:
        return await self.global_messages(
            q=q,
            folder_id=int(folder_id),
            limit=limit,
            timeout=timeout,
        )

    async def replies_recent(
        self,
        peer: PeerRef,
        msg_id: int,
        *,
        limit: int = 20,
        timeout: float = 20.0,
    ) -> Any:
        return await self.discussion_replies(
            peer,
            msg_id,
            limit=int(limit),
            timeout=timeout,
        )
