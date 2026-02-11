from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from telecraft.client.peers import PeerRef

NotifyTargetKind = Literal["peer", "users", "chats", "broadcasts", "forum_topic"]


@dataclass(frozen=True, slots=True)
class NotifyTarget:
    kind: NotifyTargetKind
    peer: PeerRef | None = None
    top_msg_id: int | None = None

    @classmethod
    def peer_target(cls, peer: PeerRef) -> NotifyTarget:
        return cls(kind="peer", peer=peer)

    @classmethod
    def users(cls) -> NotifyTarget:
        return cls(kind="users")

    @classmethod
    def chats(cls) -> NotifyTarget:
        return cls(kind="chats")

    @classmethod
    def broadcasts(cls) -> NotifyTarget:
        return cls(kind="broadcasts")

    @classmethod
    def forum_topic(cls, peer: PeerRef, top_msg_id: int) -> NotifyTarget:
        return cls(kind="forum_topic", peer=peer, top_msg_id=int(top_msg_id))
