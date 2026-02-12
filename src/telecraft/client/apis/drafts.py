from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from telecraft.client.apis._utils import resolve_input_peer
from telecraft.client.peers import PeerRef
from telecraft.tl.generated.functions import (
    MessagesClearAllDrafts,
    MessagesGetAllDrafts,
    MessagesGetPeerDialogs,
    MessagesSaveDraft,
)
from telecraft.tl.generated.types import InputDialogPeer, InputMessageReplyTo

if TYPE_CHECKING:
    from telecraft.client.mtproto import MtprotoClient


class DraftsAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def list(self, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(MessagesGetAllDrafts(), timeout=timeout)

    async def get(self, peer: PeerRef, *, timeout: float = 20.0) -> Any:
        input_peer = await resolve_input_peer(self._raw, peer, timeout=timeout)
        return await self._raw.invoke_api(
            MessagesGetPeerDialogs(peers=[InputDialogPeer(peer=input_peer)]),
            timeout=timeout,
        )

    async def save(
        self,
        peer: PeerRef,
        *,
        text: str = "",
        reply_to_msg_id: int | None = None,
        no_webpage: bool = False,
        entities: Sequence[Any] | None = None,
        media: Any | None = None,
        timeout: float = 20.0,
    ) -> Any:
        flags = 0
        if no_webpage:
            flags |= 2
        if reply_to_msg_id is not None:
            flags |= 1
        if entities is not None:
            flags |= 8
        if media is not None:
            flags |= 16

        reply_to = (
            InputMessageReplyTo(id=int(reply_to_msg_id))
            if reply_to_msg_id is not None
            else None
        )

        return await self._raw.invoke_api(
            MessagesSaveDraft(
                flags=flags,
                no_webpage=True if no_webpage else None,
                invert_media=None,
                reply_to=reply_to,
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                message=str(text),
                entities=list(entities) if entities is not None else None,
                media=media,
                effect=None,
                suggested_post=None,
            ),
            timeout=timeout,
        )

    async def clear(self, peer: PeerRef, *, timeout: float = 20.0) -> Any:
        return await self.save(peer, text="", timeout=timeout)

    async def clear_all(self, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(MessagesClearAllDrafts(), timeout=timeout)

    async def save_no_webpage(
        self,
        peer: PeerRef,
        text: str = "",
        *,
        timeout: float = 20.0,
    ) -> Any:
        return await self.save(peer, text=text, no_webpage=True, timeout=timeout)

    async def has_draft(self, peer: PeerRef, *, timeout: float = 20.0) -> bool:
        out = await self.get(peer, timeout=timeout)
        return out is not None

    async def clear_if_any(self, peer: PeerRef, *, timeout: float = 20.0) -> Any:
        _ = await self.has_draft(peer, timeout=timeout)
        return await self.clear(peer, timeout=timeout)
