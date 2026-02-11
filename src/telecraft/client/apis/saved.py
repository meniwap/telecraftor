from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from telecraft.client.apis._utils import resolve_input_peer
from telecraft.client.peers import PeerRef
from telecraft.tl.generated.functions import (
    MessagesGetPinnedSavedDialogs,
    MessagesGetSavedDialogs,
    MessagesGetSavedDialogsById,
    MessagesGetSavedGifs,
    MessagesGetSavedHistory,
    MessagesGetSavedReactionTags,
    MessagesReorderPinnedSavedDialogs,
    MessagesToggleSavedDialogPin,
)
from telecraft.tl.generated.types import InputDialogPeer, InputPeerSelf

if TYPE_CHECKING:
    from telecraft.client.mtproto import MtprotoClient


class SavedGifsAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def list(self, *, hash: int = 0, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            MessagesGetSavedGifs(hash=int(hash)),
            timeout=timeout,
        )


class SavedDialogsAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def list(
        self,
        *,
        limit: int = 100,
        offset_id: int = 0,
        offset_date: int = 0,
        offset_peer: PeerRef | None = None,
        exclude_pinned: bool = False,
        parent_peer: PeerRef | None = None,
        hash: int = 0,
        timeout: float = 20.0,
    ) -> Any:
        flags = 0
        if exclude_pinned:
            flags |= 1
        parent_input = None
        if parent_peer is not None:
            flags |= 2
            parent_input = await resolve_input_peer(self._raw, parent_peer, timeout=timeout)

        if offset_peer is None:
            offset_input = InputPeerSelf()
        else:
            offset_input = await resolve_input_peer(self._raw, offset_peer, timeout=timeout)

        return await self._raw.invoke_api(
            MessagesGetSavedDialogs(
                flags=flags,
                exclude_pinned=True if exclude_pinned else None,
                parent_peer=parent_input,
                offset_date=int(offset_date),
                offset_id=int(offset_id),
                offset_peer=offset_input,
                limit=int(limit),
                hash=int(hash),
            ),
            timeout=timeout,
        )

    async def by_id(
        self,
        ids: Sequence[PeerRef],
        *,
        parent_peer: PeerRef | None = None,
        timeout: float = 20.0,
    ) -> Any:
        if not ids:
            raise ValueError("ids cannot be empty")

        flags = 0
        parent_input = None
        if parent_peer is not None:
            flags |= 1
            parent_input = await resolve_input_peer(self._raw, parent_peer, timeout=timeout)

        input_ids: list[Any] = []
        for ref in ids:
            input_peer = await resolve_input_peer(self._raw, ref, timeout=timeout)
            input_ids.append(input_peer)

        return await self._raw.invoke_api(
            MessagesGetSavedDialogsById(
                flags=flags,
                parent_peer=parent_input,
                ids=input_ids,
            ),
            timeout=timeout,
        )


class SavedHistoryAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def list(
        self,
        peer: PeerRef,
        *,
        limit: int = 100,
        offset_id: int = 0,
        offset_date: int = 0,
        add_offset: int = 0,
        max_id: int = 0,
        min_id: int = 0,
        parent_peer: PeerRef | None = None,
        hash: int = 0,
        timeout: float = 20.0,
    ) -> Any:
        flags = 0
        parent_input = None
        if parent_peer is not None:
            flags |= 1
            parent_input = await resolve_input_peer(self._raw, parent_peer, timeout=timeout)

        input_peer = await resolve_input_peer(self._raw, peer, timeout=timeout)

        return await self._raw.invoke_api(
            MessagesGetSavedHistory(
                flags=flags,
                parent_peer=parent_input,
                peer=input_peer,
                offset_id=int(offset_id),
                offset_date=int(offset_date),
                add_offset=int(add_offset),
                limit=int(limit),
                max_id=int(max_id),
                min_id=int(min_id),
                hash=int(hash),
            ),
            timeout=timeout,
        )


class SavedReactionTagsAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def list(
        self,
        *,
        peer: PeerRef | None = None,
        hash: int = 0,
        timeout: float = 20.0,
    ) -> Any:
        flags = 0
        input_peer = None
        if peer is not None:
            flags |= 1
            input_peer = await resolve_input_peer(self._raw, peer, timeout=timeout)

        return await self._raw.invoke_api(
            MessagesGetSavedReactionTags(
                flags=flags,
                peer=input_peer,
                hash=int(hash),
            ),
            timeout=timeout,
        )


class SavedPinnedAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def list(self, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(MessagesGetPinnedSavedDialogs(), timeout=timeout)

    async def pin(self, peer: PeerRef, *, pinned: bool = True, timeout: float = 20.0) -> Any:
        input_peer = await resolve_input_peer(self._raw, peer, timeout=timeout)
        flags = 1 if pinned else 0
        return await self._raw.invoke_api(
            MessagesToggleSavedDialogPin(
                flags=flags,
                pinned=True if pinned else None,
                peer=InputDialogPeer(peer=input_peer),
            ),
            timeout=timeout,
        )

    async def reorder(
        self,
        order: Sequence[PeerRef],
        *,
        force: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        input_order: list[Any] = []
        for ref in order:
            input_peer = await resolve_input_peer(self._raw, ref, timeout=timeout)
            input_order.append(InputDialogPeer(peer=input_peer))

        flags = 1 if force else 0
        return await self._raw.invoke_api(
            MessagesReorderPinnedSavedDialogs(
                flags=flags,
                force=True if force else None,
                order=input_order,
            ),
            timeout=timeout,
        )


class SavedAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw
        self.gifs = SavedGifsAPI(raw)
        self.dialogs = SavedDialogsAPI(raw)
        self.history = SavedHistoryAPI(raw)
        self.reaction_tags = SavedReactionTagsAPI(raw)
        self.pinned = SavedPinnedAPI(raw)
