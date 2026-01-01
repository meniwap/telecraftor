from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias

PeerType: TypeAlias = Literal["user", "chat", "channel"]


@dataclass(frozen=True, slots=True)
class Peer:
    """
    High-level peer reference (Telethon/Pyrogram-style abstraction).

    - user: private chat with a user (requires access_hash to build InputPeerUser)
    - chat: basic group chat (InputPeerChat doesn't need access_hash)
    - channel: channel/supergroup (requires access_hash to build InputPeerChannel/InputChannel)
    """

    peer_type: PeerType
    peer_id: int

    @classmethod
    def user(cls, user_id: int) -> Peer:
        return cls("user", int(user_id))

    @classmethod
    def chat(cls, chat_id: int) -> Peer:
        return cls("chat", int(chat_id))

    @classmethod
    def channel(cls, channel_id: int) -> Peer:
        return cls("channel", int(channel_id))


PeerRef: TypeAlias = Peer | tuple[PeerType, int] | str | int


def normalize_username(username: str) -> str:
    u = username.strip()
    if u.startswith("@"):
        u = u[1:]
    return u.strip().lower()


def normalize_phone(phone: str) -> str:
    p = phone.strip()
    if not p:
        return p
    # Keep a leading '+' when provided; otherwise keep digits only.
    if p.startswith("+"):
        return "+" + "".join(ch for ch in p[1:] if ch.isdigit())
    return "".join(ch for ch in p if ch.isdigit())


def peer_from_tl_peer(peer_obj: object) -> Peer | None:
    """
    Convert a TL Peer (peerUser/peerChat/peerChannel) into Peer.
    """
    name = getattr(peer_obj, "TL_NAME", None)
    if name == "peerUser":
        v = getattr(peer_obj, "user_id", None)
        return Peer.user(int(v)) if isinstance(v, int) else None
    if name == "peerChat":
        v = getattr(peer_obj, "chat_id", None)
        return Peer.chat(int(v)) if isinstance(v, int) else None
    if name == "peerChannel":
        v = getattr(peer_obj, "channel_id", None)
        return Peer.channel(int(v)) if isinstance(v, int) else None
    return None


