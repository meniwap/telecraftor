from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from telecraft.client.peers import PeerRef

GiftRefKind = Literal["user_msg", "chat_saved", "slug"]


@dataclass(frozen=True, slots=True)
class GiftRef:
    kind: GiftRefKind
    msg_id: int | None = None
    peer: PeerRef | None = None
    saved_id: int | None = None
    slug_value: str | None = None

    @classmethod
    def user_msg(cls, msg_id: int) -> GiftRef:
        return cls(kind="user_msg", msg_id=int(msg_id))

    @classmethod
    def chat_saved(cls, peer: PeerRef, saved_id: int) -> GiftRef:
        return cls(kind="chat_saved", peer=peer, saved_id=int(saved_id))

    @classmethod
    def slug(cls, slug: str) -> GiftRef:
        s = str(slug).strip()
        if not s:
            raise ValueError("slug cannot be empty")
        return cls(kind="slug", slug_value=s)
