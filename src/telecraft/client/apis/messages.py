from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from telecraft.client.peers import PeerRef

if TYPE_CHECKING:
    from telecraft.client.mtproto import MtprotoClient


class MessagesAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def send(
        self,
        peer: PeerRef,
        text: str,
        *,
        reply_to_msg_id: int | None = None,
        silent: bool = False,
        reply_markup: Any | None = None,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.send_message(
            peer,
            text,
            reply_to_msg_id=reply_to_msg_id,
            silent=silent,
            reply_markup=reply_markup,
            timeout=timeout,
        )

    async def send_self(
        self,
        text: str,
        *,
        reply_to_msg_id: int | None = None,
        silent: bool = False,
        reply_markup: Any | None = None,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.send_message_self(
            text,
            reply_to_msg_id=reply_to_msg_id,
            silent=silent,
            reply_markup=reply_markup,
            timeout=timeout,
        )

    async def send_chat(
        self,
        chat_id: int,
        text: str,
        *,
        reply_to_msg_id: int | None = None,
        silent: bool = False,
        reply_markup: Any | None = None,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.send_message_chat(
            chat_id,
            text,
            reply_to_msg_id=reply_to_msg_id,
            silent=silent,
            reply_markup=reply_markup,
            timeout=timeout,
        )

    async def send_user(
        self,
        user_id: int,
        text: str,
        *,
        reply_to_msg_id: int | None = None,
        silent: bool = False,
        reply_markup: Any | None = None,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.send_message_user(
            user_id,
            text,
            reply_to_msg_id=reply_to_msg_id,
            silent=silent,
            reply_markup=reply_markup,
            timeout=timeout,
        )

    async def send_channel(
        self,
        channel_id: int,
        text: str,
        *,
        reply_to_msg_id: int | None = None,
        silent: bool = False,
        reply_markup: Any | None = None,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.send_message_channel(
            channel_id,
            text,
            reply_to_msg_id=reply_to_msg_id,
            silent=silent,
            reply_markup=reply_markup,
            timeout=timeout,
        )

    async def send_peer(
        self,
        peer: Any,
        text: str,
        *,
        reply_to_msg_id: int | None = None,
        silent: bool = False,
        reply_markup: Any | None = None,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.send_message_peer(
            peer,
            text,
            reply_to_msg_id=reply_to_msg_id,
            silent=silent,
            reply_markup=reply_markup,
            timeout=timeout,
        )

    async def forward(
        self,
        *,
        from_peer: PeerRef,
        to_peer: PeerRef,
        msg_ids: int | list[int],
        drop_author: bool = False,
        drop_captions: bool = False,
        silent: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.forward_messages(
            from_peer=from_peer,
            to_peer=to_peer,
            msg_ids=msg_ids,
            drop_author=drop_author,
            drop_captions=drop_captions,
            silent=silent,
            timeout=timeout,
        )

    async def delete(
        self,
        peer: PeerRef,
        msg_ids: int | list[int],
        *,
        revoke: bool = True,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.delete_messages(peer, msg_ids, revoke=revoke, timeout=timeout)

    async def edit(
        self,
        peer: PeerRef,
        msg_id: int,
        text: str,
        *,
        no_webpage: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.edit_message(
            peer,
            msg_id,
            text,
            no_webpage=no_webpage,
            timeout=timeout,
        )

    async def pin(
        self,
        peer: PeerRef,
        msg_id: int,
        *,
        unpin: bool = False,
        silent: bool = False,
        pm_oneside: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.pin_message(
            peer,
            msg_id,
            unpin=unpin,
            silent=silent,
            pm_oneside=pm_oneside,
            timeout=timeout,
        )

    async def react(
        self,
        peer: PeerRef,
        msg_id: int,
        *,
        reaction: str | list[str] | None = None,
        emoji: str | list[str] | None = None,
        big: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        if reaction is not None and emoji is not None:
            raise ValueError("Pass only one of reaction or emoji")
        resolved = reaction if reaction is not None else emoji
        return await self._raw.send_reaction(
            peer,
            msg_id,
            reaction=resolved,
            big=big,
            timeout=timeout,
        )

    async def search(
        self,
        peer: PeerRef,
        *,
        query: str = "",
        from_user: PeerRef | None = None,
        offset_id: int = 0,
        limit: int = 100,
        min_date: int = 0,
        max_date: int = 0,
        timeout: float = 20.0,
    ) -> list[Any]:
        return await self._raw.search_messages(
            peer,
            query=query,
            from_user=from_user,
            offset_id=offset_id,
            limit=limit,
            min_date=min_date,
            max_date=max_date,
            timeout=timeout,
        )

    async def mark_read(self, peer: PeerRef, *, max_id: int = 0, timeout: float = 20.0) -> Any:
        return await self._raw.mark_read(peer, max_id=max_id, timeout=timeout)

    async def history(
        self,
        peer: PeerRef,
        *,
        limit: int = 50,
        timeout: float = 20.0,
    ) -> list[Any]:
        return await self._raw.get_history(
            peer,
            limit=limit,
            timeout=timeout,
        )

    async def iter_dialogs(
        self,
        *,
        limit: int = 100,
        folder_id: int | None = None,
        timeout: float = 20.0,
    ) -> AsyncIterator[Any]:
        async for item in self._raw.iter_dialogs(limit=limit, folder_id=folder_id, timeout=timeout):
            yield item

    async def iter_messages(
        self,
        peer: PeerRef,
        *,
        limit: int = 100,
        timeout: float = 20.0,
    ) -> AsyncIterator[Any]:
        async for item in self._raw.iter_messages(peer, limit=limit, timeout=timeout):
            yield item
