from __future__ import annotations

from typing import TYPE_CHECKING, Any

from telecraft.client.peers import PeerRef
from telecraft.tl.generated.types import ChatAdminRights, ChatBannedRights

if TYPE_CHECKING:
    from telecraft.client.mtproto import MtprotoClient


class AdminAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def edit(
        self,
        channel: PeerRef,
        user: PeerRef,
        *,
        rights: ChatAdminRights,
        rank: str = "",
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.edit_admin(
            channel,
            user,
            admin_rights=rights,
            rank=rank,
            timeout=timeout,
        )

    async def restrict(
        self,
        channel: PeerRef,
        user: PeerRef,
        *,
        rights: ChatBannedRights,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.edit_banned(
            channel,
            user,
            banned_rights=rights,
            timeout=timeout,
        )

    async def promote(
        self,
        channel: PeerRef,
        user: PeerRef,
        *,
        change_info: bool = True,
        post_messages: bool = True,
        edit_messages: bool = True,
        delete_messages: bool = True,
        ban_users: bool = True,
        invite_users: bool = True,
        pin_messages: bool = True,
        add_admins: bool = False,
        anonymous: bool = False,
        manage_call: bool = True,
        manage_topics: bool = True,
        rank: str = "",
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.promote_admin(
            channel,
            user,
            change_info=change_info,
            post_messages=post_messages,
            edit_messages=edit_messages,
            delete_messages=delete_messages,
            ban_users=ban_users,
            invite_users=invite_users,
            pin_messages=pin_messages,
            add_admins=add_admins,
            anonymous=anonymous,
            manage_call=manage_call,
            manage_topics=manage_topics,
            rank=rank,
            timeout=timeout,
        )

    async def demote(self, channel: PeerRef, user: PeerRef, *, timeout: float = 20.0) -> Any:
        return await self._raw.demote_admin(channel, user, timeout=timeout)

    async def ban(
        self,
        channel: PeerRef,
        user: PeerRef,
        *,
        until_date: int = 0,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.ban_user(channel, user, until_date=until_date, timeout=timeout)

    async def unban(self, channel: PeerRef, user: PeerRef, *, timeout: float = 20.0) -> Any:
        return await self._raw.unban_user(channel, user, timeout=timeout)

    async def kick(self, channel: PeerRef, user: PeerRef, *, timeout: float = 20.0) -> Any:
        return await self._raw.kick_user(channel, user, timeout=timeout)

    async def member(self, channel: PeerRef, user: PeerRef, *, timeout: float = 20.0) -> Any:
        return await self._raw.get_chat_member(channel, user, timeout=timeout)
