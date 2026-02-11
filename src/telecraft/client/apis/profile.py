from __future__ import annotations

from typing import TYPE_CHECKING, Any

from telecraft.client.peers import PeerRef
from telecraft.tl.generated.functions import (
    AccountClearRecentEmojiStatuses,
    AccountGetChannelDefaultEmojiStatuses,
    AccountGetDefaultEmojiStatuses,
    AccountGetRecentEmojiStatuses,
    AccountUpdateEmojiStatus,
)

if TYPE_CHECKING:
    from telecraft.client.mtproto import MtprotoClient


class ProfileEmojiStatusAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def defaults(self, *, hash: int = 0, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            AccountGetDefaultEmojiStatuses(hash=int(hash)),
            timeout=timeout,
        )

    async def recent(self, *, hash: int = 0, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(AccountGetRecentEmojiStatuses(hash=int(hash)), timeout=timeout)

    async def channel_defaults(self, *, hash: int = 0, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            AccountGetChannelDefaultEmojiStatuses(hash=int(hash)),
            timeout=timeout,
        )

    async def clear_recent(self, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(AccountClearRecentEmojiStatuses(), timeout=timeout)

    async def update(self, status: Any, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(AccountUpdateEmojiStatus(emoji_status=status), timeout=timeout)


class ProfileAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw
        self.emoji_status = ProfileEmojiStatusAPI(raw)

    async def me(self, *, timeout: float = 20.0) -> Any:
        return await self._raw.get_me(timeout=timeout)

    async def user_info(self, user: PeerRef, *, timeout: float = 20.0) -> Any:
        return await self._raw.get_user_info(user, timeout=timeout)

    async def chat_info(self, peer: PeerRef, *, timeout: float = 20.0) -> Any:
        return await self._raw.get_chat_info(peer, timeout=timeout)

    async def photos(
        self,
        user: PeerRef,
        *,
        offset: int = 0,
        limit: int = 100,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.get_profile_photos(user, offset=offset, limit=limit, timeout=timeout)

    async def upload_photo(self, path: str, *, timeout: float = 60.0) -> Any:
        return await self._raw.upload_profile_photo(path, timeout=timeout)

    async def delete_photos(
        self,
        photo_ids: list[tuple[int, int]] | tuple[int, int],
        *,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.delete_profile_photos(photo_ids, timeout=timeout)
