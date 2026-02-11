from __future__ import annotations

from typing import TYPE_CHECKING, Any

from telecraft.client.peers import PeerRef

if TYPE_CHECKING:
    from telecraft.client.mtproto import MtprotoClient


class PollsAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def send(
        self,
        peer: PeerRef,
        *,
        question: str,
        options: list[str],
        multiple_choice: bool = False,
        public_voters: bool = False,
        close_period: int | None = None,
        close_date: int | None = None,
        reply_to_msg_id: int | None = None,
        silent: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.send_poll(
            peer,
            question=question,
            options=options,
            multiple_choice=multiple_choice,
            public_voters=public_voters,
            close_period=close_period,
            close_date=close_date,
            reply_to_msg_id=reply_to_msg_id,
            silent=silent,
            timeout=timeout,
        )

    async def send_quiz(
        self,
        peer: PeerRef,
        *,
        question: str,
        options: list[str],
        correct_option: int,
        explanation: str | None = None,
        public_voters: bool = False,
        close_period: int | None = None,
        reply_to_msg_id: int | None = None,
        silent: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.send_quiz(
            peer,
            question=question,
            options=options,
            correct_option=correct_option,
            explanation=explanation,
            public_voters=public_voters,
            close_period=close_period,
            reply_to_msg_id=reply_to_msg_id,
            silent=silent,
            timeout=timeout,
        )

    async def vote(
        self,
        peer: PeerRef,
        *,
        msg_id: int,
        options: int | list[int],
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.vote_poll(peer, msg_id=msg_id, options=options, timeout=timeout)

    async def close(self, peer: PeerRef, *, msg_id: int, timeout: float = 20.0) -> Any:
        return await self._raw.close_poll(peer, msg_id=msg_id, timeout=timeout)

    async def results(self, peer: PeerRef, *, msg_id: int, timeout: float = 20.0) -> Any:
        return await self._raw.get_poll_results(peer, msg_id=msg_id, timeout=timeout)

    async def scheduled(self, peer: PeerRef, *, timeout: float = 20.0) -> list[Any]:
        return await self._raw.get_scheduled_messages(peer, timeout=timeout)

    async def delete_scheduled(
        self,
        peer: PeerRef,
        *,
        msg_ids: int | list[int],
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.delete_scheduled_messages(peer, msg_ids=msg_ids, timeout=timeout)

    async def send_scheduled_now(
        self,
        peer: PeerRef,
        *,
        msg_ids: int | list[int],
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.send_scheduled_now(peer, msg_ids=msg_ids, timeout=timeout)

