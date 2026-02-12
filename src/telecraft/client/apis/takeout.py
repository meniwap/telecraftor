from __future__ import annotations

from typing import TYPE_CHECKING, Any

from telecraft.client.apis._utils import resolve_input_peer
from telecraft.client.peers import PeerRef
from telecraft.client.takeout import TakeoutScopes, TakeoutSessionRef, build_takeout_flags
from telecraft.tl.generated.functions import (
    AccountFinishTakeoutSession,
    AccountInitTakeoutSession,
    InvokeWithTakeout,
    MessagesGetHistory,
)

if TYPE_CHECKING:
    from telecraft.client.mtproto import MtprotoClient


class TakeoutMessagesAPI:
    def __init__(self, parent: TakeoutAPI) -> None:
        self._parent = parent

    async def export(
        self,
        peer: PeerRef,
        *,
        limit: int = 0,
        timeout: float = 20.0,
    ) -> Any:
        req = MessagesGetHistory(
            peer=await resolve_input_peer(self._parent.raw, peer, timeout=timeout),
            offset_id=0,
            offset_date=0,
            add_offset=0,
            limit=int(limit),
            max_id=0,
            min_id=0,
            hash=0,
        )
        return await self._parent.invoke(req, timeout=timeout)

    async def export_latest(
        self,
        peer: PeerRef,
        *,
        timeout: float = 20.0,
    ) -> Any:
        return await self.export(peer, limit=1, timeout=timeout)


class TakeoutMediaAPI:
    def __init__(self, parent: TakeoutAPI) -> None:
        self._parent = parent

    async def export(
        self,
        peer: PeerRef,
        *,
        limit: int = 0,
        timeout: float = 20.0,
    ) -> Any:
        req = MessagesGetHistory(
            peer=await resolve_input_peer(self._parent.raw, peer, timeout=timeout),
            offset_id=0,
            offset_date=0,
            add_offset=0,
            limit=int(limit),
            max_id=0,
            min_id=0,
            hash=0,
        )
        return await self._parent.invoke(req, timeout=timeout)

    async def export_latest(
        self,
        peer: PeerRef,
        *,
        timeout: float = 20.0,
    ) -> Any:
        return await self.export(peer, limit=1, timeout=timeout)


class TakeoutAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self.raw = raw
        self._takeout_id: int | None = None
        self.messages = TakeoutMessagesAPI(self)
        self.media = TakeoutMediaAPI(self)

    @property
    def session(self) -> TakeoutSessionRef | None:
        if self._takeout_id is None:
            return None
        return TakeoutSessionRef.from_id(self._takeout_id)

    async def start(
        self,
        scopes: TakeoutScopes | None = None,
        *,
        file_max_size: int | None = None,
        timeout: float = 20.0,
    ) -> Any:
        effective_scopes = scopes or TakeoutScopes()
        flags = build_takeout_flags(effective_scopes)
        if file_max_size is not None:
            flags |= 64
        res = await self.raw.invoke_api(
            AccountInitTakeoutSession(
                flags=flags,
                contacts=True if effective_scopes.contacts else None,
                message_users=True if effective_scopes.message_users else None,
                message_chats=True if effective_scopes.message_chats else None,
                message_megagroups=True if effective_scopes.message_megagroups else None,
                message_channels=True if effective_scopes.message_channels else None,
                files=True if effective_scopes.files else None,
                file_max_size=int(file_max_size) if file_max_size is not None else None,
            ),
            timeout=timeout,
        )
        takeout_id = getattr(res, "id", None)
        if isinstance(takeout_id, int):
            self._takeout_id = int(takeout_id)
        return res

    async def invoke(
        self,
        query_obj: Any,
        *,
        takeout_id: int | None = None,
        timeout: float = 20.0,
    ) -> Any:
        selected = int(takeout_id) if takeout_id is not None else self._takeout_id
        if selected is None:
            selected = 0
        return await self.raw.invoke_api(
            InvokeWithTakeout(takeout_id=int(selected), query=query_obj),
            timeout=timeout,
        )

    async def finish(self, *, success: bool = True, timeout: float = 20.0) -> Any:
        flags = 1 if success else 0
        return await self.raw.invoke_api(
            AccountFinishTakeoutSession(flags=flags, success=True if success else None),
            timeout=timeout,
        )
