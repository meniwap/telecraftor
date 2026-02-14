from __future__ import annotations

from dataclasses import dataclass

from telecraft.client.peers import PeerRef


@dataclass(frozen=True, slots=True)
class FolderAssignment:
    peer: PeerRef
    folder_id: int

    @classmethod
    def of(cls, peer: PeerRef, folder_id: int) -> FolderAssignment:
        return cls(peer=peer, folder_id=int(folder_id))
