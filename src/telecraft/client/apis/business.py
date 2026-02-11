from __future__ import annotations

import secrets
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from telecraft.client.apis._utils import resolve_input_peer
from telecraft.client.peers import PeerRef
from telecraft.tl.generated.functions import (
    AccountCreateBusinessChatLink,
    AccountDeleteBusinessChatLink,
    AccountEditBusinessChatLink,
    AccountGetBusinessChatLinks,
    AccountResolveBusinessChatLink,
    AccountUpdateBusinessAwayMessage,
    AccountUpdateBusinessGreetingMessage,
    AccountUpdateBusinessIntro,
    AccountUpdateBusinessLocation,
    AccountUpdateBusinessWorkHours,
    MessagesCheckQuickReplyShortcut,
    MessagesDeleteQuickReplyMessages,
    MessagesDeleteQuickReplyShortcut,
    MessagesEditQuickReplyShortcut,
    MessagesGetQuickReplies,
    MessagesGetQuickReplyMessages,
    MessagesReorderQuickReplies,
    MessagesSendQuickReplyMessages,
)

if TYPE_CHECKING:
    from telecraft.client.mtproto import MtprotoClient


class BusinessLinksAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def list(self, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(AccountGetBusinessChatLinks(), timeout=timeout)

    async def create(self, link_obj: Any, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(AccountCreateBusinessChatLink(link=link_obj), timeout=timeout)

    async def edit(self, slug: str, link_obj: Any, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            AccountEditBusinessChatLink(slug=str(slug), link=link_obj),
            timeout=timeout,
        )

    async def delete(self, slug: str, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            AccountDeleteBusinessChatLink(slug=str(slug)),
            timeout=timeout,
        )

    async def resolve(self, slug: str, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            AccountResolveBusinessChatLink(slug=str(slug)),
            timeout=timeout,
        )


class BusinessProfileAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def update_intro(self, intro_obj_or_none: Any | None, *, timeout: float = 20.0) -> Any:
        flags = 1 if intro_obj_or_none is not None else 0
        return await self._raw.invoke_api(
            AccountUpdateBusinessIntro(flags=flags, intro=intro_obj_or_none),
            timeout=timeout,
        )

    async def update_location(
        self,
        *,
        address: str | None = None,
        geo_point: Any | None = None,
        timeout: float = 20.0,
    ) -> Any:
        flags = 0
        if address is not None:
            flags |= 1
        if geo_point is not None:
            flags |= 2
        return await self._raw.invoke_api(
            AccountUpdateBusinessLocation(
                flags=flags,
                geo_point=geo_point,
                address=address,
            ),
            timeout=timeout,
        )

    async def update_work_hours(self, work_hours_obj_or_none: Any | None, *, timeout: float = 20.0) -> Any:
        flags = 1 if work_hours_obj_or_none is not None else 0
        return await self._raw.invoke_api(
            AccountUpdateBusinessWorkHours(
                flags=flags,
                business_work_hours=work_hours_obj_or_none,
            ),
            timeout=timeout,
        )

    async def update_greeting(self, message_obj_or_none: Any | None, *, timeout: float = 20.0) -> Any:
        flags = 1 if message_obj_or_none is not None else 0
        return await self._raw.invoke_api(
            AccountUpdateBusinessGreetingMessage(flags=flags, message=message_obj_or_none),
            timeout=timeout,
        )

    async def update_away(self, message_obj_or_none: Any | None, *, timeout: float = 20.0) -> Any:
        flags = 1 if message_obj_or_none is not None else 0
        return await self._raw.invoke_api(
            AccountUpdateBusinessAwayMessage(flags=flags, message=message_obj_or_none),
            timeout=timeout,
        )


class BusinessQuickRepliesAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def list(self, *, hash: int = 0, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(MessagesGetQuickReplies(hash=int(hash)), timeout=timeout)

    async def reorder(self, order: Sequence[int], *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            MessagesReorderQuickReplies(order=[int(x) for x in order]),
            timeout=timeout,
        )

    async def check_shortcut(self, shortcut: str, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            MessagesCheckQuickReplyShortcut(shortcut=str(shortcut)),
            timeout=timeout,
        )

    async def edit_shortcut(self, shortcut_id: int, shortcut: str, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            MessagesEditQuickReplyShortcut(shortcut_id=int(shortcut_id), shortcut=str(shortcut)),
            timeout=timeout,
        )

    async def delete_shortcut(self, shortcut_id: int, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            MessagesDeleteQuickReplyShortcut(shortcut_id=int(shortcut_id)),
            timeout=timeout,
        )

    async def get_messages(
        self,
        shortcut_id: int,
        *,
        ids: Sequence[int] | None = None,
        hash: int = 0,
        timeout: float = 20.0,
    ) -> Any:
        flags = 1 if ids is not None else 0
        return await self._raw.invoke_api(
            MessagesGetQuickReplyMessages(
                flags=flags,
                shortcut_id=int(shortcut_id),
                id=[int(x) for x in ids] if ids is not None else None,
                hash=int(hash),
            ),
            timeout=timeout,
        )

    async def send(
        self,
        peer: PeerRef,
        shortcut_id: int,
        ids: Sequence[int],
        *,
        timeout: float = 20.0,
    ) -> Any:
        id_list = [int(x) for x in ids]
        random_id = [secrets.randbits(63) for _ in id_list]
        return await self._raw.invoke_api(
            MessagesSendQuickReplyMessages(
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                shortcut_id=int(shortcut_id),
                id=id_list,
                random_id=random_id,
            ),
            timeout=timeout,
        )

    async def delete_messages(self, shortcut_id: int, ids: Sequence[int], *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            MessagesDeleteQuickReplyMessages(
                shortcut_id=int(shortcut_id),
                id=[int(x) for x in ids],
            ),
            timeout=timeout,
        )


class BusinessAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw
        self.links = BusinessLinksAPI(raw)
        self.profile = BusinessProfileAPI(raw)
        self.quick_replies = BusinessQuickRepliesAPI(raw)
