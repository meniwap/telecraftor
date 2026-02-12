from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from telecraft.client.apis._utils import resolve_input_peer
from telecraft.client.peers import PeerRef
from telecraft.tl.generated.functions import MessagesTranslateText
from telecraft.tl.generated.types import InputPeerEmpty

if TYPE_CHECKING:
    from telecraft.client.mtproto import MtprotoClient


class TranslateAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def text(
        self,
        text: str = "",
        to_lang: str = "en",
        *,
        from_lang: str | None = None,
        peer: PeerRef | None = None,
        timeout: float = 20.0,
    ) -> Any:
        _ = from_lang
        flags = 0
        input_peer: Any = InputPeerEmpty()
        if peer is not None:
            flags |= 1
            input_peer = await resolve_input_peer(self._raw, peer, timeout=timeout)
        return await self._raw.invoke_api(
            MessagesTranslateText(
                flags=flags,
                peer=input_peer if peer is not None else None,
                id=None,
                text=[str(text)],
                to_lang=str(to_lang),
            ),
            timeout=timeout,
        )

    async def messages(
        self,
        peer: PeerRef,
        msg_ids: Sequence[int],
        to_lang: str = "en",
        *,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            MessagesTranslateText(
                flags=1,
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                id=[int(x) for x in msg_ids],
                text=None,
                to_lang=str(to_lang),
            ),
            timeout=timeout,
        )

    async def text_auto(
        self,
        text: str = "",
        to_lang: str = "en",
        *,
        timeout: float = 20.0,
    ) -> Any:
        return await self.text(text, to_lang, timeout=timeout)

    async def messages_auto(
        self,
        peer: PeerRef,
        msg_ids: Sequence[int],
        to_lang: str = "en",
        *,
        timeout: float = 20.0,
    ) -> Any:
        return await self.messages(peer, msg_ids, to_lang, timeout=timeout)
