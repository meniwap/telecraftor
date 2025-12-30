from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from telecraft.tl.generated.types import (
    InputPeerChannel,
    InputPeerChat,
    InputPeerSelf,
    InputPeerUser,
)


class EntityCacheError(Exception):
    pass


@dataclass(slots=True)
class EntityCache:
    """
    Minimal entity cache for building InputPeer*.

    For users/channels, Telegram requires `access_hash` to build InputPeerUser/InputPeerChannel.
    """

    user_access_hash: dict[int, int] = field(default_factory=dict)
    channel_access_hash: dict[int, int] = field(default_factory=dict)

    def ingest_users(self, users: list[Any]) -> None:
        for u in users:
            uid = getattr(u, "id", None)
            ah = getattr(u, "access_hash", None)
            if isinstance(uid, int) and isinstance(ah, int) and ah != 0:
                self.user_access_hash[int(uid)] = int(ah)

    def ingest_chats(self, chats: list[Any]) -> None:
        for c in chats:
            # channels need access_hash; basic chats don't.
            tl_name = getattr(c, "TL_NAME", None)
            if tl_name in {"channel", "channelForbidden"}:
                cid = getattr(c, "id", None)
                ah = getattr(c, "access_hash", None)
                if isinstance(cid, int) and isinstance(ah, int) and ah != 0:
                    self.channel_access_hash[int(cid)] = int(ah)

    def input_peer_self(self) -> InputPeerSelf:
        return InputPeerSelf()

    def input_peer_user(self, user_id: int) -> InputPeerUser:
        ah = self.user_access_hash.get(int(user_id))
        if ah is None:
            raise EntityCacheError(f"Unknown user access_hash for user_id={user_id}")
        return InputPeerUser(user_id=int(user_id), access_hash=int(ah))

    def input_peer_channel(self, channel_id: int) -> InputPeerChannel:
        ah = self.channel_access_hash.get(int(channel_id))
        if ah is None:
            raise EntityCacheError(f"Unknown channel access_hash for channel_id={channel_id}")
        return InputPeerChannel(channel_id=int(channel_id), access_hash=int(ah))

    def input_peer_chat(self, chat_id: int) -> InputPeerChat:
        return InputPeerChat(chat_id=int(chat_id))

