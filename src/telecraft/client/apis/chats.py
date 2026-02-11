from __future__ import annotations

from typing import TYPE_CHECKING, Any

from telecraft.client.entities import EntityCacheError
from telecraft.client.peers import PeerRef
from telecraft.tl.generated.functions import ChannelsDeleteChannel, MessagesDeleteChat

if TYPE_CHECKING:
    from telecraft.client.mtproto import MtprotoClient


class ChatMembersAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def add(
        self,
        group: PeerRef,
        user: PeerRef,
        *,
        fwd_limit: int = 50,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.add_user_to_group(group, user, fwd_limit=fwd_limit, timeout=timeout)

    async def add_many(
        self,
        group: PeerRef,
        users: list[PeerRef],
        *,
        on_error: str = "skip",
        timeout: float = 20.0,
    ) -> dict[str, Any]:
        return await self._raw.add_users_to_group(
            group,
            users,
            on_error=on_error,
            timeout=timeout,
        )

    async def remove(self, group: PeerRef, user: PeerRef, *, timeout: float = 20.0) -> Any:
        return await self._raw.remove_user_from_group(group, user, timeout=timeout)

    async def list(self, group: PeerRef, *, limit: int = 200, timeout: float = 20.0) -> list[Any]:
        return await self._raw.get_group_members(group, limit=limit, timeout=timeout)

    async def transfer(
        self,
        *,
        from_group: PeerRef,
        to_group: PeerRef,
        limit: int | None = None,
        exclude_bots: bool = True,
        exclude_self: bool = True,
        on_error: str = "skip",
        timeout: float = 20.0,
    ) -> dict[str, Any]:
        _ = exclude_self
        return await self._raw.transfer_members(
            from_group=from_group,
            to_group=to_group,
            limit=limit,
            exclude_bots=exclude_bots,
            exclude_admins=False,
            on_error=on_error,
            timeout=timeout,
        )


class ChatInvitesAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def create(
        self,
        peer: PeerRef,
        *,
        expire_date: int | None = None,
        usage_limit: int | None = None,
        request_needed: bool = False,
        title: str | None = None,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.create_invite_link(
            peer,
            expire_date=expire_date,
            usage_limit=usage_limit,
            request_needed=request_needed,
            title=title,
            timeout=timeout,
        )

    async def revoke(self, peer: PeerRef, link: str, *, timeout: float = 20.0) -> Any:
        return await self._raw.revoke_invite_link(peer, link, timeout=timeout)

    async def delete(self, peer: PeerRef, link: str, *, timeout: float = 20.0) -> Any:
        return await self._raw.delete_invite_link(peer, link, timeout=timeout)

    async def list(
        self,
        peer: PeerRef,
        *,
        limit: int = 100,
        revoked: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.get_invite_links(
            peer,
            limit=limit,
            revoked=revoked,
            timeout=timeout,
        )


class ChatsAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw
        self.members = ChatMembersAPI(raw)
        self.invites = ChatInvitesAPI(raw)

    async def create_group(self, title: str, users: list[PeerRef], *, timeout: float = 20.0) -> Any:
        return await self._raw.create_group(title, users, timeout=timeout)

    async def create_channel(
        self,
        title: str,
        about: str = "",
        *,
        broadcast: bool = True,
        megagroup: bool = False,
        forum: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.create_channel(
            title,
            about,
            broadcast=broadcast,
            megagroup=megagroup,
            forum=forum,
            timeout=timeout,
        )

    async def set_title(self, peer: PeerRef, title: str, *, timeout: float = 20.0) -> Any:
        return await self._raw.set_chat_title(peer, title, timeout=timeout)

    async def common(self, user: PeerRef, *, limit: int = 100, timeout: float = 20.0) -> list[Any]:
        return await self._raw.get_common_chats(user, limit=limit, timeout=timeout)

    async def join(self, channel: PeerRef, *, timeout: float = 20.0) -> Any:
        return await self._raw.join_channel(channel, timeout=timeout)

    async def leave(self, channel: PeerRef, *, timeout: float = 20.0) -> Any:
        return await self._raw.leave_channel(channel, timeout=timeout)

    async def delete_history(
        self,
        peer: PeerRef,
        *,
        revoke: bool = True,
        just_clear: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.delete_chat_history(
            peer,
            revoke=revoke,
            just_clear=just_clear,
            timeout=timeout,
        )

    async def delete_group(self, chat_id: int, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(MessagesDeleteChat(chat_id=int(chat_id)), timeout=timeout)

    async def delete_channel(self, channel: PeerRef, *, timeout: float = 20.0) -> Any:
        p = await self._raw.resolve_peer(channel, timeout=timeout)
        if p.peer_type != "channel":
            raise ValueError("delete_channel expects a channel peer")
        try:
            input_channel = self._raw.entities.input_channel(int(p.peer_id))
        except EntityCacheError:
            await self._raw.prime_entities(limit=200, timeout=timeout)
            input_channel = self._raw.entities.input_channel(int(p.peer_id))
        return await self._raw.invoke_api(
            ChannelsDeleteChannel(channel=input_channel),
            timeout=timeout,
        )
