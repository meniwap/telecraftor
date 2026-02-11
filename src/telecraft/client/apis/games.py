from __future__ import annotations

from typing import TYPE_CHECKING, Any

from telecraft.client.apis._utils import resolve_input_peer, resolve_input_user
from telecraft.client.peers import PeerRef
from telecraft.tl.generated.functions import (
    MessagesGetGameHighScores,
    MessagesSetGameScore,
    MessagesSetInlineGameScore,
)

if TYPE_CHECKING:
    from telecraft.client.mtproto import MtprotoClient


class GameScoresAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def set(
        self,
        peer: PeerRef,
        msg_id: int,
        user: PeerRef,
        score: int,
        *,
        edit_message: bool = False,
        force: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        input_peer = await resolve_input_peer(self._raw, peer, timeout=timeout)
        input_user = await resolve_input_user(self._raw, user, timeout=timeout)

        flags = 0
        if edit_message:
            flags |= 1
        if force:
            flags |= 2

        return await self._raw.invoke_api(
            MessagesSetGameScore(
                flags=flags,
                edit_message=True if edit_message else None,
                force=True if force else None,
                peer=input_peer,
                id=int(msg_id),
                user_id=input_user,
                score=int(score),
            ),
            timeout=timeout,
        )

    async def set_inline(
        self,
        inline_message_id: Any,
        user: PeerRef,
        score: int,
        *,
        edit_message: bool = False,
        force: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        input_user = await resolve_input_user(self._raw, user, timeout=timeout)

        flags = 0
        if edit_message:
            flags |= 1
        if force:
            flags |= 2

        return await self._raw.invoke_api(
            MessagesSetInlineGameScore(
                flags=flags,
                edit_message=True if edit_message else None,
                force=True if force else None,
                id=inline_message_id,
                user_id=input_user,
                score=int(score),
            ),
            timeout=timeout,
        )

    async def high_scores(
        self,
        peer: PeerRef,
        msg_id: int,
        user: PeerRef,
        *,
        timeout: float = 20.0,
    ) -> Any:
        input_peer = await resolve_input_peer(self._raw, peer, timeout=timeout)
        input_user = await resolve_input_user(self._raw, user, timeout=timeout)

        return await self._raw.invoke_api(
            MessagesGetGameHighScores(
                peer=input_peer,
                id=int(msg_id),
                user_id=input_user,
            ),
            timeout=timeout,
        )


class GamesAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw
        self.scores = GameScoresAPI(raw)

    async def send(
        self,
        peer: PeerRef,
        *,
        emoji: str = "\U0001f3b2",
        reply_to_msg_id: int | None = None,
        silent: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.send_dice(
            peer,
            emoji=emoji,
            reply_to_msg_id=reply_to_msg_id,
            silent=silent,
            timeout=timeout,
        )

    async def throw_darts(
        self,
        peer: PeerRef,
        *,
        reply_to_msg_id: int | None = None,
        silent: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.throw_darts(
            peer,
            reply_to_msg_id=reply_to_msg_id,
            silent=silent,
            timeout=timeout,
        )

    async def roll_dice(
        self,
        peer: PeerRef,
        *,
        reply_to_msg_id: int | None = None,
        silent: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.roll_dice(
            peer,
            reply_to_msg_id=reply_to_msg_id,
            silent=silent,
            timeout=timeout,
        )

    async def roll_bowling(
        self,
        peer: PeerRef,
        *,
        reply_to_msg_id: int | None = None,
        silent: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.roll_bowling(
            peer,
            reply_to_msg_id=reply_to_msg_id,
            silent=silent,
            timeout=timeout,
        )

    async def kick_football(
        self,
        peer: PeerRef,
        *,
        reply_to_msg_id: int | None = None,
        silent: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.kick_football(
            peer,
            reply_to_msg_id=reply_to_msg_id,
            silent=silent,
            timeout=timeout,
        )

    async def shoot_basketball(
        self,
        peer: PeerRef,
        *,
        reply_to_msg_id: int | None = None,
        silent: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.shoot_basketball(
            peer,
            reply_to_msg_id=reply_to_msg_id,
            silent=silent,
            timeout=timeout,
        )

    async def spin_slot_machine(
        self,
        peer: PeerRef,
        *,
        reply_to_msg_id: int | None = None,
        silent: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.spin_slot_machine(
            peer,
            reply_to_msg_id=reply_to_msg_id,
            silent=silent,
            timeout=timeout,
        )
