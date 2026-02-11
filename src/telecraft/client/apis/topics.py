from __future__ import annotations

import secrets
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from telecraft.client.apis._utils import resolve_input_channel, resolve_input_peer
from telecraft.client.peers import PeerRef
from telecraft.tl.generated.functions import (
    ChannelsToggleForum,
    ChannelsToggleViewForumAsMessages,
    MessagesCreateForumTopic,
    MessagesDeleteTopicHistory,
    MessagesEditForumTopic,
    MessagesGetForumTopics,
    MessagesGetForumTopicsById,
    MessagesReorderPinnedForumTopics,
    MessagesUpdatePinnedForumTopic,
)

if TYPE_CHECKING:
    from telecraft.client.mtproto import MtprotoClient


class TopicsForumAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def toggle(
        self,
        channel: PeerRef,
        *,
        enabled: bool = True,
        tabs: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            ChannelsToggleForum(
                channel=await resolve_input_channel(self._raw, channel, timeout=timeout),
                enabled=bool(enabled),
                tabs=bool(tabs),
            ),
            timeout=timeout,
        )

    async def view_as_messages(
        self,
        channel: PeerRef,
        *,
        enabled: bool = True,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            ChannelsToggleViewForumAsMessages(
                channel=await resolve_input_channel(self._raw, channel, timeout=timeout),
                enabled=bool(enabled),
            ),
            timeout=timeout,
        )


class TopicsAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw
        self.forum = TopicsForumAPI(raw)

    async def list(
        self,
        peer: PeerRef,
        *,
        q: str | None = None,
        offset_date: int = 0,
        offset_id: int = 0,
        offset_topic: int = 0,
        limit: int = 100,
        timeout: float = 20.0,
    ) -> Any:
        flags = 1 if q is not None else 0
        return await self._raw.invoke_api(
            MessagesGetForumTopics(
                flags=flags,
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                q=q,
                offset_date=int(offset_date),
                offset_id=int(offset_id),
                offset_topic=int(offset_topic),
                limit=int(limit),
            ),
            timeout=timeout,
        )

    async def by_id(self, peer: PeerRef, topics: Sequence[int], *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            MessagesGetForumTopicsById(
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                topics=[int(topic) for topic in topics],
            ),
            timeout=timeout,
        )

    async def create(
        self,
        peer: PeerRef,
        title: str,
        *,
        icon_color: int | None = None,
        icon_emoji_id: int | None = None,
        send_as: PeerRef | None = None,
        timeout: float = 20.0,
    ) -> Any:
        flags = 0
        send_as_input = None
        if icon_color is not None:
            flags |= 1
        if send_as is not None:
            flags |= 4
            send_as_input = await resolve_input_peer(self._raw, send_as, timeout=timeout)
        if icon_emoji_id is not None:
            flags |= 8
        if not str(title).strip():
            flags |= 16
        return await self._raw.invoke_api(
            MessagesCreateForumTopic(
                flags=flags,
                title_missing=True if not str(title).strip() else None,
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                title=str(title),
                icon_color=int(icon_color) if icon_color is not None else None,
                icon_emoji_id=int(icon_emoji_id) if icon_emoji_id is not None else None,
                random_id=secrets.randbits(63),
                send_as=send_as_input,
            ),
            timeout=timeout,
        )

    async def edit(
        self,
        peer: PeerRef,
        topic_id: int,
        *,
        title: str | None = None,
        icon_emoji_id: int | None = None,
        closed: bool | None = None,
        hidden: bool | None = None,
        timeout: float = 20.0,
    ) -> Any:
        flags = 0
        if title is not None:
            flags |= 1
        if icon_emoji_id is not None:
            flags |= 2
        if closed is not None:
            flags |= 4
        if hidden is not None:
            flags |= 8
        return await self._raw.invoke_api(
            MessagesEditForumTopic(
                flags=flags,
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                topic_id=int(topic_id),
                title=title,
                icon_emoji_id=int(icon_emoji_id) if icon_emoji_id is not None else None,
                closed=bool(closed) if closed is not None else None,
                hidden=bool(hidden) if hidden is not None else None,
            ),
            timeout=timeout,
        )

    async def pin(
        self,
        peer: PeerRef,
        topic_id: int,
        *,
        pinned: bool = True,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            MessagesUpdatePinnedForumTopic(
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                topic_id=int(topic_id),
                pinned=bool(pinned),
            ),
            timeout=timeout,
        )

    async def reorder(
        self,
        peer: PeerRef,
        order: Sequence[int],
        *,
        force: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        flags = 1 if force else 0
        return await self._raw.invoke_api(
            MessagesReorderPinnedForumTopics(
                flags=flags,
                force=True if force else None,
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                order=[int(topic_id) for topic_id in order],
            ),
            timeout=timeout,
        )

    async def delete_history(self, peer: PeerRef, top_msg_id: int, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            MessagesDeleteTopicHistory(
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                top_msg_id=int(top_msg_id),
            ),
            timeout=timeout,
        )
