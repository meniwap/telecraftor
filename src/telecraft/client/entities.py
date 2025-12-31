from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from telecraft.tl.generated.types import (
    InputPeerChannel,
    InputPeerChat,
    InputPeerSelf,
    InputPeerUser,
)


class EntityCacheError(Exception):
    pass


class EntityCacheStorageError(Exception):
    pass


_ENTITY_CACHE_VERSION = 1


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

    def to_json_dict(self) -> dict[str, object]:
        return {
            "version": _ENTITY_CACHE_VERSION,
            "user_access_hash": {str(k): int(v) for k, v in self.user_access_hash.items()},
            "channel_access_hash": {str(k): int(v) for k, v in self.channel_access_hash.items()},
        }

    @classmethod
    def from_json_dict(cls, data: dict[str, object]) -> EntityCache:
        try:
            version_obj = data.get("version", _ENTITY_CACHE_VERSION)
            if not isinstance(version_obj, (int, str)):
                raise EntityCacheStorageError("Invalid version")
            version = int(version_obj)
            if version != _ENTITY_CACHE_VERSION:
                raise EntityCacheStorageError(f"Unsupported entity cache version: {version}")

            ua = data.get("user_access_hash", {})
            ca = data.get("channel_access_hash", {})
            if not isinstance(ua, dict) or not isinstance(ca, dict):
                raise EntityCacheStorageError("Invalid cache dicts")

            user_access_hash: dict[int, int] = {}
            for k, v in ua.items():
                if not isinstance(k, str) or not isinstance(v, (int, str)):
                    continue
                user_access_hash[int(k)] = int(v)

            channel_access_hash: dict[int, int] = {}
            for k, v in ca.items():
                if not isinstance(k, str) or not isinstance(v, (int, str)):
                    continue
                channel_access_hash[int(k)] = int(v)
        except Exception as e:  # noqa: BLE001
            raise EntityCacheStorageError("Invalid entity cache JSON shape") from e

        out = cls()
        out.user_access_hash = user_access_hash
        out.channel_access_hash = channel_access_hash
        return out


def load_entity_cache_file(path: str | Path) -> EntityCache:
    p = Path(path)
    raw = p.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except Exception as e:  # noqa: BLE001
        raise EntityCacheStorageError(f"Failed to parse entity cache JSON: {p}") from e
    if not isinstance(data, dict):
        raise EntityCacheStorageError("Entity cache JSON must be an object")
    return EntityCache.from_json_dict(data)


def save_entity_cache_file(path: str | Path, cache: EntityCache) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(
        json.dumps(cache.to_json_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    tmp.replace(p)

