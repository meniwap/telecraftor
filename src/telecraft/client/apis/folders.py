from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from telecraft.client.apis._utils import resolve_input_peer
from telecraft.client.folders import FolderAssignment
from telecraft.client.peers import PeerRef
from telecraft.tl.generated.functions import FoldersEditPeerFolders
from telecraft.tl.generated.types import InputFolderPeer

if TYPE_CHECKING:
    from telecraft.client.mtproto import MtprotoClient


async def _input_folder_peer(
    raw: MtprotoClient,
    peer: PeerRef,
    folder_id: int,
    *,
    timeout: float,
) -> InputFolderPeer:
    return InputFolderPeer(
        peer=await resolve_input_peer(raw, peer, timeout=timeout),
        folder_id=int(folder_id),
    )


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

    async def assign(self, peer: PeerRef, folder_id: int, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            FoldersEditPeerFolders(
                folder_peers=[
                    await _input_folder_peer(
                        self._raw,
                        peer,
                        int(folder_id),
                        timeout=timeout,
                    )
                ]
            ),
            timeout=timeout,
        )

    async def assign_many(
        self,
        assignments: Sequence[FolderAssignment | tuple[PeerRef, int]],
        *,
        timeout: float = 20.0,
    ) -> Any:
        folder_peers: list[InputFolderPeer] = []
        for assignment in assignments:
            if isinstance(assignment, FolderAssignment):
                peer_ref = assignment.peer
                folder_id = int(assignment.folder_id)
            else:
                peer_ref, raw_folder_id = assignment
                folder_id = int(raw_folder_id)
            folder_peers.append(
                await _input_folder_peer(self._raw, peer_ref, folder_id, timeout=timeout)
            )

        return await self._raw.invoke_api(
            FoldersEditPeerFolders(folder_peers=folder_peers),
            timeout=timeout,
        )

    async def join(self, peer: PeerRef, folder_id: int, *, timeout: float = 20.0) -> Any:
        return await self.assign(peer, folder_id, timeout=timeout)

    async def leave(self, peer: PeerRef, *, timeout: float = 20.0) -> Any:
        return await self.assign(peer, 0, timeout=timeout)

    async def archive(self, peer: PeerRef, *, timeout: float = 20.0) -> Any:
        return await self.assign(peer, 1, timeout=timeout)

    async def unarchive(self, peer: PeerRef, *, timeout: float = 20.0) -> Any:
        return await self.assign(peer, 0, timeout=timeout)

    async def archive_many(self, peers: Sequence[PeerRef], *, timeout: float = 20.0) -> Any:
        assignments = [FolderAssignment.of(peer, 1) for peer in peers]
        return await self.assign_many(assignments, timeout=timeout)

    async def unarchive_many(self, peers: Sequence[PeerRef], *, timeout: float = 20.0) -> Any:
        assignments = [FolderAssignment.of(peer, 0) for peer in peers]
        return await self.assign_many(assignments, timeout=timeout)
