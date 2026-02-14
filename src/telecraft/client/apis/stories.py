from __future__ import annotations

import secrets
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from telecraft.client.apis._utils import resolve_input_peer
from telecraft.client.peers import PeerRef
from telecraft.tl.generated.functions import (
    StoriesActivateStealthMode,
    StoriesCanSendStory,
    StoriesCreateAlbum,
    StoriesDeleteAlbum,
    StoriesDeleteStories,
    StoriesEditStory,
    StoriesExportStoryLink,
    StoriesGetAlbums,
    StoriesGetAllReadPeerStories,
    StoriesGetAllStories,
    StoriesGetChatsToSend,
    StoriesGetPeerMaxIds,
    StoriesGetPeerStories,
    StoriesGetPinnedStories,
    StoriesGetStoriesArchive,
    StoriesGetStoriesById,
    StoriesGetStoriesViews,
    StoriesGetStoryReactionsList,
    StoriesGetStoryViewsList,
    StoriesIncrementStoryViews,
    StoriesReadStories,
    StoriesReorderAlbums,
    StoriesReport,
    StoriesSearchPosts,
    StoriesSendReaction,
    StoriesSendStory,
    StoriesToggleAllStoriesHidden,
    StoriesTogglePeerStoriesHidden,
    StoriesTogglePinned,
    StoriesTogglePinnedToTop,
    StoriesUpdateAlbum,
)

if TYPE_CHECKING:
    from telecraft.client.mtproto import MtprotoClient


class StoriesCapabilitiesAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def can_send(self, peer: PeerRef, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            StoriesCanSendStory(peer=await resolve_input_peer(self._raw, peer, timeout=timeout)),
            timeout=timeout,
        )


class StoriesFeedAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def all(
        self,
        *,
        next: bool = False,
        hidden: bool = False,
        state: str | None = None,
        timeout: float = 20.0,
    ) -> Any:
        flags = 0
        if state is not None:
            flags |= 1
        if next:
            flags |= 2
        if hidden:
            flags |= 4
        return await self._raw.invoke_api(
            StoriesGetAllStories(
                flags=flags,
                next=True if next else None,
                hidden=True if hidden else None,
                state=state,
            ),
            timeout=timeout,
        )

    async def peer(self, peer: PeerRef, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            StoriesGetPeerStories(peer=await resolve_input_peer(self._raw, peer, timeout=timeout)),
            timeout=timeout,
        )

    async def archive(
        self,
        peer: PeerRef,
        *,
        offset_id: int = 0,
        limit: int = 100,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            StoriesGetStoriesArchive(
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                offset_id=int(offset_id),
                limit=int(limit),
            ),
            timeout=timeout,
        )

    async def pinned(
        self,
        peer: PeerRef,
        *,
        offset_id: int = 0,
        limit: int = 100,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            StoriesGetPinnedStories(
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                offset_id=int(offset_id),
                limit=int(limit),
            ),
            timeout=timeout,
        )

    async def by_id(self, peer: PeerRef, ids: Sequence[int], *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            StoriesGetStoriesById(
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                id=[int(x) for x in ids],
            ),
            timeout=timeout,
        )


class StoriesLinksAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def export(self, peer: PeerRef, story_id: int, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            StoriesExportStoryLink(
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                id=int(story_id),
            ),
            timeout=timeout,
        )


class StoriesViewsAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def __call__(self, peer: PeerRef, ids: Sequence[int], *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            StoriesGetStoriesViews(
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                id=[int(x) for x in ids],
            ),
            timeout=timeout,
        )

    async def list(
        self,
        peer: PeerRef,
        story_id: int,
        *,
        q: str | None = None,
        offset: str = "",
        limit: int = 100,
        just_contacts: bool = False,
        reactions_first: bool = False,
        forwards_first: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        flags = 0
        if just_contacts:
            flags |= 1
        if q is not None:
            flags |= 2
        if reactions_first:
            flags |= 4
        if forwards_first:
            flags |= 8
        return await self._raw.invoke_api(
            StoriesGetStoryViewsList(
                flags=flags,
                just_contacts=True if just_contacts else None,
                reactions_first=True if reactions_first else None,
                forwards_first=True if forwards_first else None,
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                q=str(q) if q is not None else None,
                id=int(story_id),
                offset=str(offset),
                limit=int(limit),
            ),
            timeout=timeout,
        )


class StoriesReactionsAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def list(
        self,
        peer: PeerRef,
        story_id: int,
        *,
        reaction: Any | None = None,
        offset: str = "",
        limit: int = 100,
        forwards_first: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        flags = 0
        if reaction is not None:
            flags |= 1
        if offset:
            flags |= 2
        if forwards_first:
            flags |= 4
        return await self._raw.invoke_api(
            StoriesGetStoryReactionsList(
                flags=flags,
                forwards_first=True if forwards_first else None,
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                id=int(story_id),
                reaction=reaction,
                offset=str(offset) if offset else None,
                limit=int(limit),
            ),
            timeout=timeout,
        )


class StoriesStealthAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def activate(
        self,
        *,
        past: bool = False,
        future: bool = True,
        timeout: float = 20.0,
    ) -> Any:
        flags = 0
        if past:
            flags |= 1
        if future:
            flags |= 2
        return await self._raw.invoke_api(
            StoriesActivateStealthMode(
                flags=flags,
                past=True if past else None,
                future=True if future else None,
            ),
            timeout=timeout,
        )


class StoriesPeersAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def max_ids(self, peers: Sequence[PeerRef], *, timeout: float = 20.0) -> Any:
        ids = [await resolve_input_peer(self._raw, peer, timeout=timeout) for peer in peers]
        return await self._raw.invoke_api(StoriesGetPeerMaxIds(id=ids), timeout=timeout)


class StoriesAlbumsAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def list(self, peer: PeerRef, *, hash: int = 0, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            StoriesGetAlbums(
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                hash=int(hash),
            ),
            timeout=timeout,
        )

    async def create(
        self,
        peer: PeerRef,
        title: str,
        stories: Sequence[int],
        *,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            StoriesCreateAlbum(
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                title=str(title),
                stories=[int(item) for item in stories],
            ),
            timeout=timeout,
        )

    async def update(
        self,
        peer: PeerRef,
        album_id: int,
        *,
        title: str | None = None,
        add_stories: Sequence[int] | None = None,
        delete_stories: Sequence[int] | None = None,
        order: Sequence[int] | None = None,
        timeout: float = 20.0,
    ) -> Any:
        flags = 0
        if title is not None:
            flags |= 1
        if delete_stories is not None:
            flags |= 2
        if add_stories is not None:
            flags |= 4
        if order is not None:
            flags |= 8
        return await self._raw.invoke_api(
            StoriesUpdateAlbum(
                flags=flags,
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                album_id=int(album_id),
                title=str(title) if title is not None else None,
                delete_stories=(
                    [int(item) for item in delete_stories] if delete_stories is not None else None
                ),
                add_stories=(
                    [int(item) for item in add_stories] if add_stories is not None else None
                ),
                order=[int(item) for item in order] if order is not None else None,
            ),
            timeout=timeout,
        )

    async def reorder(self, peer: PeerRef, order: Sequence[int], *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            StoriesReorderAlbums(
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                order=[int(item) for item in order],
            ),
            timeout=timeout,
        )

    async def delete(self, peer: PeerRef, album_id: int, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            StoriesDeleteAlbum(
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                album_id=int(album_id),
            ),
            timeout=timeout,
        )


class StoriesAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw
        self.capabilities = StoriesCapabilitiesAPI(raw)
        self.feed = StoriesFeedAPI(raw)
        self.links = StoriesLinksAPI(raw)
        setattr(self, "views", StoriesViewsAPI(raw))
        self.reactions = StoriesReactionsAPI(raw)
        self.stealth = StoriesStealthAPI(raw)
        self.peers = StoriesPeersAPI(raw)
        self.albums = StoriesAlbumsAPI(raw)

    async def read(self, peer: PeerRef, max_id: int, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            StoriesReadStories(
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                max_id=int(max_id),
            ),
            timeout=timeout,
        )

    async def views(self, peer: PeerRef, ids: Sequence[int], *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            StoriesGetStoriesViews(
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                id=[int(x) for x in ids],
            ),
            timeout=timeout,
        )

    async def toggle_all_hidden(self, hidden: bool, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            StoriesToggleAllStoriesHidden(hidden=bool(hidden)),
            timeout=timeout,
        )

    async def toggle_peer_hidden(
        self, peer: PeerRef, hidden: bool, *, timeout: float = 20.0
    ) -> Any:
        return await self._raw.invoke_api(
            StoriesTogglePeerStoriesHidden(
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                hidden=bool(hidden),
            ),
            timeout=timeout,
        )

    async def search_posts(
        self,
        *,
        hashtag: str | None = None,
        area: Any | None = None,
        peer: PeerRef | None = None,
        offset: str = "",
        limit: int = 50,
        timeout: float = 20.0,
    ) -> Any:
        flags = 0
        input_peer = None
        if hashtag is not None:
            flags |= 1
        if area is not None:
            flags |= 2
        if peer is not None:
            flags |= 4
            input_peer = await resolve_input_peer(self._raw, peer, timeout=timeout)
        return await self._raw.invoke_api(
            StoriesSearchPosts(
                flags=flags,
                hashtag=hashtag,
                area=area,
                peer=input_peer,
                offset=str(offset),
                limit=int(limit),
            ),
            timeout=timeout,
        )

    async def all_read_peers(self, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(StoriesGetAllReadPeerStories(), timeout=timeout)

    async def report(
        self,
        peer: PeerRef,
        ids: Sequence[int],
        option: bytes | str,
        *,
        message: str = "",
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            StoriesReport(
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                id=[int(item) for item in ids],
                option=option if isinstance(option, bytes) else str(option).encode(),
                message=str(message),
            ),
            timeout=timeout,
        )

    async def chats_to_send(self, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(StoriesGetChatsToSend(), timeout=timeout)

    async def send(
        self,
        peer: PeerRef,
        media: Any,
        privacy_rules: Sequence[Any],
        *,
        caption: str | None = None,
        entities: Sequence[Any] | None = None,
        media_areas: Sequence[Any] | None = None,
        pinned: bool = False,
        noforwards: bool = False,
        fwd_modified: bool = False,
        period: int | None = None,
        fwd_from_id: PeerRef | None = None,
        fwd_from_story: int | None = None,
        albums: Sequence[int] | None = None,
        timeout: float = 20.0,
    ) -> Any:
        flags = 0
        fwd_from_input = None
        if caption is not None or entities is not None:
            flags |= 1
        if pinned:
            flags |= 4
        if period is not None:
            flags |= 8
        if noforwards:
            flags |= 16
        if media_areas is not None:
            flags |= 32
        if fwd_from_id is not None or fwd_from_story is not None:
            flags |= 64
            if fwd_from_id is not None:
                fwd_from_input = await resolve_input_peer(self._raw, fwd_from_id, timeout=timeout)
        if fwd_modified:
            flags |= 128
        if albums is not None:
            flags |= 256

        return await self._raw.invoke_api(
            StoriesSendStory(
                flags=flags,
                pinned=True if pinned else None,
                noforwards=True if noforwards else None,
                fwd_modified=True if fwd_modified else None,
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                media=media,
                media_areas=list(media_areas) if media_areas is not None else None,
                caption=caption,
                entities=list(entities) if entities is not None else None,
                privacy_rules=list(privacy_rules),
                random_id=secrets.randbits(63),
                period=int(period) if period is not None else None,
                fwd_from_id=fwd_from_input,
                fwd_from_story=int(fwd_from_story) if fwd_from_story is not None else None,
                albums=[int(x) for x in albums] if albums is not None else None,
            ),
            timeout=timeout,
        )

    async def edit(
        self,
        peer: PeerRef,
        story_id: int,
        *,
        media: Any | None = None,
        media_areas: Sequence[Any] | None = None,
        caption: str | None = None,
        entities: Sequence[Any] | None = None,
        privacy_rules: Sequence[Any] | None = None,
        timeout: float = 20.0,
    ) -> Any:
        flags = 0
        if media is not None:
            flags |= 1
        if caption is not None or entities is not None:
            flags |= 2
        if privacy_rules is not None:
            flags |= 4
        if media_areas is not None:
            flags |= 8
        return await self._raw.invoke_api(
            StoriesEditStory(
                flags=flags,
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                id=int(story_id),
                media=media,
                media_areas=list(media_areas) if media_areas is not None else None,
                caption=caption,
                entities=list(entities) if entities is not None else None,
                privacy_rules=list(privacy_rules) if privacy_rules is not None else None,
            ),
            timeout=timeout,
        )

    async def delete(self, peer: PeerRef, ids: Sequence[int], *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            StoriesDeleteStories(
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                id=[int(x) for x in ids],
            ),
            timeout=timeout,
        )

    async def pin(
        self,
        peer: PeerRef,
        ids: Sequence[int],
        *,
        pinned: bool = True,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            StoriesTogglePinned(
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                id=[int(x) for x in ids],
                pinned=bool(pinned),
            ),
            timeout=timeout,
        )

    async def pin_to_top(self, peer: PeerRef, ids: Sequence[int], *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            StoriesTogglePinnedToTop(
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                id=[int(x) for x in ids],
            ),
            timeout=timeout,
        )

    async def react(
        self,
        peer: PeerRef,
        story_id: int,
        reaction: Any,
        *,
        add_to_recent: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        flags = 1 if add_to_recent else 0
        return await self._raw.invoke_api(
            StoriesSendReaction(
                flags=flags,
                add_to_recent=True if add_to_recent else None,
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                story_id=int(story_id),
                reaction=reaction,
            ),
            timeout=timeout,
        )

    async def increment_views(
        self, peer: PeerRef, ids: Sequence[int], *, timeout: float = 20.0
    ) -> Any:
        return await self._raw.invoke_api(
            StoriesIncrementStoryViews(
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                id=[int(x) for x in ids],
            ),
            timeout=timeout,
        )
