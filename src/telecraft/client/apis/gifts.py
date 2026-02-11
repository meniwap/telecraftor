from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from telecraft.client.apis._utils import resolve_input_peer, resolve_input_peer_or_self
from telecraft.client.gifts import GiftRef
from telecraft.client.peers import PeerRef
from telecraft.tl.generated.functions import (
    PaymentsCheckCanSendGift,
    PaymentsConvertStarGift,
    PaymentsGetResaleStarGifts,
    PaymentsGetSavedStarGift,
    PaymentsGetSavedStarGifts,
    PaymentsGetStarGiftCollections,
    PaymentsGetStarGifts,
    PaymentsGetStarGiftUpgradePreview,
    PaymentsGetUniqueStarGift,
    PaymentsSaveStarGift,
    PaymentsTransferStarGift,
    PaymentsUpgradeStarGift,
)
from telecraft.tl.generated.types import (
    InputSavedStarGiftChat,
    InputSavedStarGiftSlug,
    InputSavedStarGiftUser,
)

if TYPE_CHECKING:
    from telecraft.client.mtproto import MtprotoClient


async def _gift_ref_to_input(raw: MtprotoClient, ref: GiftRef, *, timeout: float) -> Any:
    if ref.kind == "user_msg":
        if ref.msg_id is None:
            raise ValueError("GiftRef.user_msg requires msg_id")
        return InputSavedStarGiftUser(msg_id=int(ref.msg_id))
    if ref.kind == "chat_saved":
        if ref.peer is None or ref.saved_id is None:
            raise ValueError("GiftRef.chat_saved requires peer and saved_id")
        input_peer = await resolve_input_peer(raw, ref.peer, timeout=timeout)
        return InputSavedStarGiftChat(peer=input_peer, saved_id=int(ref.saved_id))
    if ref.kind == "slug":
        if not ref.slug_value:
            raise ValueError("GiftRef.slug requires slug value")
        return InputSavedStarGiftSlug(slug=str(ref.slug_value))
    raise ValueError(f"Unsupported GiftRef kind: {ref.kind!r}")


class GiftsSavedAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def list(
        self,
        *,
        peer: PeerRef | str = "self",
        offset: str = "",
        limit: int = 100,
        collection_id: int | None = None,
        exclude_unsaved: bool = False,
        exclude_saved: bool = False,
        exclude_unlimited: bool = False,
        exclude_unique: bool = False,
        sort_by_value: bool = False,
        exclude_upgradable: bool = False,
        exclude_unupgradable: bool = False,
        peer_color_available: bool = False,
        exclude_hosted: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        input_peer = await resolve_input_peer_or_self(self._raw, peer, timeout=timeout)

        flags = 0
        if exclude_unsaved:
            flags |= 1
        if exclude_saved:
            flags |= 2
        if exclude_unlimited:
            flags |= 4
        if exclude_unique:
            flags |= 16
        if sort_by_value:
            flags |= 32
        if collection_id is not None:
            flags |= 64
        if exclude_upgradable:
            flags |= 128
        if exclude_unupgradable:
            flags |= 256
        if peer_color_available:
            flags |= 512
        if exclude_hosted:
            flags |= 1024

        return await self._raw.invoke_api(
            PaymentsGetSavedStarGifts(
                flags=flags,
                exclude_unsaved=True if exclude_unsaved else None,
                exclude_saved=True if exclude_saved else None,
                exclude_unlimited=True if exclude_unlimited else None,
                exclude_unique=True if exclude_unique else None,
                sort_by_value=True if sort_by_value else None,
                exclude_upgradable=True if exclude_upgradable else None,
                exclude_unupgradable=True if exclude_unupgradable else None,
                peer_color_available=True if peer_color_available else None,
                exclude_hosted=True if exclude_hosted else None,
                peer=input_peer,
                collection_id=collection_id,
                offset=str(offset),
                limit=int(limit),
            ),
            timeout=timeout,
        )

    async def get(self, refs: Sequence[GiftRef], *, timeout: float = 20.0) -> Any:
        if not refs:
            raise ValueError("refs cannot be empty")

        inputs = [await _gift_ref_to_input(self._raw, ref, timeout=timeout) for ref in refs]
        return await self._raw.invoke_api(
            PaymentsGetSavedStarGift(stargift=inputs),
            timeout=timeout,
        )

    async def save(self, ref: GiftRef, *, unsave: bool = False, timeout: float = 20.0) -> Any:
        input_ref = await _gift_ref_to_input(self._raw, ref, timeout=timeout)
        flags = 1 if unsave else 0
        return await self._raw.invoke_api(
            PaymentsSaveStarGift(
                flags=flags,
                unsave=True if unsave else None,
                stargift=input_ref,
            ),
            timeout=timeout,
        )

    async def convert(self, ref: GiftRef, *, timeout: float = 20.0) -> Any:
        input_ref = await _gift_ref_to_input(self._raw, ref, timeout=timeout)
        return await self._raw.invoke_api(
            PaymentsConvertStarGift(stargift=input_ref),
            timeout=timeout,
        )

    async def transfer(self, ref: GiftRef, to_peer: PeerRef, *, timeout: float = 20.0) -> Any:
        input_ref = await _gift_ref_to_input(self._raw, ref, timeout=timeout)
        input_to = await resolve_input_peer(self._raw, to_peer, timeout=timeout)
        return await self._raw.invoke_api(
            PaymentsTransferStarGift(stargift=input_ref, to_id=input_to),
            timeout=timeout,
        )

    async def upgrade_preview(self, gift_id: int, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            PaymentsGetStarGiftUpgradePreview(gift_id=int(gift_id)),
            timeout=timeout,
        )

    async def upgrade(
        self,
        ref: GiftRef,
        *,
        keep_original_details: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        input_ref = await _gift_ref_to_input(self._raw, ref, timeout=timeout)
        flags = 1 if keep_original_details else 0
        return await self._raw.invoke_api(
            PaymentsUpgradeStarGift(
                flags=flags,
                keep_original_details=True if keep_original_details else None,
                stargift=input_ref,
            ),
            timeout=timeout,
        )


class GiftsResaleAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def list(
        self,
        gift_id: int,
        *,
        offset: str = "",
        limit: int = 50,
        sort_by_price: bool = False,
        sort_by_num: bool = False,
        attributes_hash: int | None = None,
        attributes: Sequence[Any] | None = None,
        timeout: float = 20.0,
    ) -> Any:
        flags = 0
        if attributes_hash is not None:
            flags |= 1
        if sort_by_price:
            flags |= 2
        if sort_by_num:
            flags |= 4
        if attributes is not None:
            flags |= 8

        return await self._raw.invoke_api(
            PaymentsGetResaleStarGifts(
                flags=flags,
                sort_by_price=True if sort_by_price else None,
                sort_by_num=True if sort_by_num else None,
                attributes_hash=attributes_hash,
                gift_id=int(gift_id),
                attributes=list(attributes) if attributes is not None else None,
                offset=str(offset),
                limit=int(limit),
            ),
            timeout=timeout,
        )


class GiftsUniqueAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def get(self, slug: str, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            PaymentsGetUniqueStarGift(slug=str(slug)),
            timeout=timeout,
        )


class GiftsAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw
        self.saved = GiftsSavedAPI(raw)
        self.resale = GiftsResaleAPI(raw)
        self.unique = GiftsUniqueAPI(raw)

    async def catalog(self, *, hash: int = 0, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(PaymentsGetStarGifts(hash=int(hash)), timeout=timeout)

    async def collections(self, peer: PeerRef, *, hash: int = 0, timeout: float = 20.0) -> Any:
        input_peer = await resolve_input_peer(self._raw, peer, timeout=timeout)
        return await self._raw.invoke_api(
            PaymentsGetStarGiftCollections(peer=input_peer, hash=int(hash)),
            timeout=timeout,
        )

    async def check_can_send(self, gift_id: int, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            PaymentsCheckCanSendGift(gift_id=int(gift_id)),
            timeout=timeout,
        )
