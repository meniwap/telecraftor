from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from telecraft.client.peers import PeerRef

if TYPE_CHECKING:
    from telecraft.client.mtproto import MtprotoClient


class FoldersAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def list(self, *, timeout: float = 20.0) -> list[Any]:
        return await self._raw.get_folders(timeout=timeout)

    async def create(
        self,
        title: str,
        *,
        folder_id: int | None = None,
        include_peers: Sequence[PeerRef] | None = None,
        exclude_peers: Sequence[PeerRef] | None = None,
        pinned_peers: Sequence[PeerRef] | None = None,
        contacts: bool = False,
        non_contacts: bool = False,
        groups: bool = False,
        channels: bool = False,
        bots: bool = False,
        exclude_muted: bool = False,
        exclude_read: bool = False,
        exclude_archived: bool = False,
        emoticon: str | None = None,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.create_folder(
            title=title,
            folder_id=folder_id,
            include_peers=list(include_peers) if include_peers is not None else None,
            exclude_peers=list(exclude_peers) if exclude_peers is not None else None,
            pinned_peers=list(pinned_peers) if pinned_peers is not None else None,
            contacts=contacts,
            non_contacts=non_contacts,
            groups=groups,
            channels=channels,
            bots=bots,
            exclude_muted=exclude_muted,
            exclude_read=exclude_read,
            exclude_archived=exclude_archived,
            emoticon=emoticon,
            timeout=timeout,
        )

    async def delete(self, folder_id: int, *, timeout: float = 20.0) -> bool:
        return await self._raw.delete_folder(folder_id, timeout=timeout)

    async def reorder(self, folder_ids: Sequence[int], *, timeout: float = 20.0) -> Any:
        return await self._raw.reorder_folders(list(folder_ids), timeout=timeout)
