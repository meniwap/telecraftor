from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from telecraft.client.apis._utils import (
    resolve_input_dialog_peer,
    resolve_input_dialog_peers,
    resolve_input_peer,
    resolve_input_peer_or_self,
)
from telecraft.client.peers import PeerRef
from telecraft.tl.generated.functions import (
    MessagesGetDialogFilters,
    MessagesGetDialogs,
    MessagesGetDialogUnreadMarks,
    MessagesGetPeerDialogs,
    MessagesGetPinnedDialogs,
    MessagesGetSuggestedDialogFilters,
    MessagesMarkDialogUnread,
    MessagesReorderPinnedDialogs,
    MessagesToggleDialogFilterTags,
    MessagesToggleDialogPin,
    MessagesUpdateDialogFilter,
    MessagesUpdateDialogFiltersOrder,
)

if TYPE_CHECKING:
    from telecraft.client.mtproto import MtprotoClient


class DialogsPinnedAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def list(self, *, folder_id: int = 0, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            MessagesGetPinnedDialogs(folder_id=int(folder_id)),
            timeout=timeout,
        )

    async def pin(
        self,
        peer: PeerRef,
        *,
        pinned: bool = True,
        timeout: float = 20.0,
    ) -> Any:
        flags = 1 if pinned else 0
        return await self._raw.invoke_api(
            MessagesToggleDialogPin(
                flags=flags,
                pinned=True if pinned else None,
                peer=await resolve_input_dialog_peer(self._raw, peer, timeout=timeout),
            ),
            timeout=timeout,
        )

    async def reorder(
        self,
        order: Sequence[PeerRef],
        *,
        folder_id: int = 0,
        force: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        flags = 1 if force else 0
        return await self._raw.invoke_api(
            MessagesReorderPinnedDialogs(
                flags=flags,
                force=True if force else None,
                folder_id=int(folder_id),
                order=await resolve_input_dialog_peers(self._raw, order, timeout=timeout),
            ),
            timeout=timeout,
        )


class DialogsUnreadAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def mark(
        self,
        peer: PeerRef,
        *,
        unread: bool = True,
        parent_peer: PeerRef | None = None,
        timeout: float = 20.0,
    ) -> Any:
        flags = 0
        parent_input = None
        if unread:
            flags |= 1
        if parent_peer is not None:
            flags |= 2
            parent_input = await resolve_input_peer(self._raw, parent_peer, timeout=timeout)

        return await self._raw.invoke_api(
            MessagesMarkDialogUnread(
                flags=flags,
                unread=True if unread else None,
                parent_peer=parent_input,
                peer=await resolve_input_dialog_peer(self._raw, peer, timeout=timeout),
            ),
            timeout=timeout,
        )

    async def marks(
        self,
        *,
        parent_peer: PeerRef | None = None,
        timeout: float = 20.0,
    ) -> Any:
        flags = 0
        parent_input = None
        if parent_peer is not None:
            flags |= 1
            parent_input = await resolve_input_peer(self._raw, parent_peer, timeout=timeout)
        return await self._raw.invoke_api(
            MessagesGetDialogUnreadMarks(
                flags=flags,
                parent_peer=parent_input,
            ),
            timeout=timeout,
        )


class DialogsFiltersAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def list(self, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(MessagesGetDialogFilters(), timeout=timeout)

    async def suggested(self, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(MessagesGetSuggestedDialogFilters(), timeout=timeout)

    async def update(
        self,
        filter_id: int,
        filter_obj_or_none: Any | None,
        *,
        timeout: float = 20.0,
    ) -> Any:
        flags = 1 if filter_obj_or_none is not None else 0
        return await self._raw.invoke_api(
            MessagesUpdateDialogFilter(
                flags=flags,
                id=int(filter_id),
                filter=filter_obj_or_none,
            ),
            timeout=timeout,
        )

    async def reorder(self, order: Sequence[int], *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            MessagesUpdateDialogFiltersOrder(order=[int(x) for x in order]),
            timeout=timeout,
        )

    async def toggle_tags(self, enabled: bool, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            MessagesToggleDialogFilterTags(enabled=bool(enabled)),
            timeout=timeout,
        )


class DialogsAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw
        self.pinned = DialogsPinnedAPI(raw)
        self.unread = DialogsUnreadAPI(raw)
        self.filters = DialogsFiltersAPI(raw)

    async def list(
        self,
        *,
        limit: int = 100,
        offset_date: int = 0,
        offset_id: int = 0,
        offset_peer: PeerRef | str = "self",
        exclude_pinned: bool = False,
        folder_id: int | None = None,
        hash: int = 0,
        timeout: float = 20.0,
    ) -> Any:
        flags = 0
        if exclude_pinned:
            flags |= 1
        if folder_id is not None:
            flags |= 2
        return await self._raw.invoke_api(
            MessagesGetDialogs(
                flags=flags,
                exclude_pinned=True if exclude_pinned else None,
                folder_id=int(folder_id) if folder_id is not None else None,
                offset_date=int(offset_date),
                offset_id=int(offset_id),
                offset_peer=await resolve_input_peer_or_self(
                    self._raw, offset_peer, timeout=timeout
                ),
                limit=int(limit),
                hash=int(hash),
            ),
            timeout=timeout,
        )

    async def by_peers(self, peers: Sequence[PeerRef], *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            MessagesGetPeerDialogs(
                peers=await resolve_input_dialog_peers(self._raw, peers, timeout=timeout),
            ),
            timeout=timeout,
        )
