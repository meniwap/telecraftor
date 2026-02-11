from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from telecraft.client.stickers import DocumentRef, StickerSetRef, build_input_document, build_input_sticker_set
from telecraft.tl.generated.functions import (
    MessagesClearRecentStickers,
    MessagesFaveSticker,
    MessagesGetAllStickers,
    MessagesGetArchivedStickers,
    MessagesGetCustomEmojiDocuments,
    MessagesGetFavedStickers,
    MessagesGetFeaturedStickers,
    MessagesGetRecentStickers,
    MessagesGetStickerSet,
    MessagesGetStickers,
    MessagesInstallStickerSet,
    MessagesReadFeaturedStickers,
    MessagesReorderStickerSets,
    MessagesSaveRecentSticker,
    MessagesSearchStickerSets,
    MessagesSearchStickers,
    MessagesUninstallStickerSet,
)

if TYPE_CHECKING:
    from telecraft.client.mtproto import MtprotoClient


class StickerSetsAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def all(self, *, hash: int = 0, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(MessagesGetAllStickers(hash=int(hash)), timeout=timeout)

    async def featured(self, *, hash: int = 0, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(MessagesGetFeaturedStickers(hash=int(hash)), timeout=timeout)

    async def read_featured(self, ids: Sequence[int], *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            MessagesReadFeaturedStickers(id=[int(x) for x in ids]),
            timeout=timeout,
        )

    async def archived(
        self,
        *,
        offset_id: int = 0,
        limit: int = 100,
        masks: bool = False,
        emojis: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        flags = 0
        if masks:
            flags |= 1
        if emojis:
            flags |= 2
        return await self._raw.invoke_api(
            MessagesGetArchivedStickers(
                flags=flags,
                masks=True if masks else None,
                emojis=True if emojis else None,
                offset_id=int(offset_id),
                limit=int(limit),
            ),
            timeout=timeout,
        )

    async def get(
        self,
        ref: StickerSetRef | Any,
        *,
        hash: int = 0,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            MessagesGetStickerSet(
                stickerset=build_input_sticker_set(ref),
                hash=int(hash),
            ),
            timeout=timeout,
        )

    async def install(
        self,
        ref: StickerSetRef | Any,
        *,
        archived: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            MessagesInstallStickerSet(
                stickerset=build_input_sticker_set(ref),
                archived=bool(archived),
            ),
            timeout=timeout,
        )

    async def uninstall(self, ref: StickerSetRef | Any, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            MessagesUninstallStickerSet(stickerset=build_input_sticker_set(ref)),
            timeout=timeout,
        )

    async def reorder(
        self,
        order: Sequence[int],
        *,
        masks: bool = False,
        emojis: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        flags = 0
        if masks:
            flags |= 1
        if emojis:
            flags |= 2
        return await self._raw.invoke_api(
            MessagesReorderStickerSets(
                flags=flags,
                masks=True if masks else None,
                emojis=True if emojis else None,
                order=[int(x) for x in order],
            ),
            timeout=timeout,
        )


class StickerSearchAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def by_emoji(self, emoticon: str, *, hash: int = 0, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            MessagesGetStickers(emoticon=str(emoticon), hash=int(hash)),
            timeout=timeout,
        )

    async def sets(
        self,
        query: str,
        *,
        hash: int = 0,
        exclude_featured: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        flags = 1 if exclude_featured else 0
        return await self._raw.invoke_api(
            MessagesSearchStickerSets(
                flags=flags,
                exclude_featured=True if exclude_featured else None,
                q=str(query),
                hash=int(hash),
            ),
            timeout=timeout,
        )

    async def stickers(
        self,
        query: str,
        *,
        emoticon: str = "",
        lang_code: Sequence[str] = (),
        offset: int = 0,
        limit: int = 100,
        hash: int = 0,
        emojis: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        flags = 1 if emojis else 0
        return await self._raw.invoke_api(
            MessagesSearchStickers(
                flags=flags,
                emojis=True if emojis else None,
                q=str(query),
                emoticon=str(emoticon),
                lang_code=[str(code) for code in lang_code],
                offset=int(offset),
                limit=int(limit),
                hash=int(hash),
            ),
            timeout=timeout,
        )


class StickerRecentAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def list(self, *, attached: bool = False, hash: int = 0, timeout: float = 20.0) -> Any:
        flags = 1 if attached else 0
        return await self._raw.invoke_api(
            MessagesGetRecentStickers(
                flags=flags,
                attached=True if attached else None,
                hash=int(hash),
            ),
            timeout=timeout,
        )

    async def save(
        self,
        document: DocumentRef | Any,
        *,
        unsave: bool = False,
        attached: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        flags = 1 if attached else 0
        return await self._raw.invoke_api(
            MessagesSaveRecentSticker(
                flags=flags,
                attached=True if attached else None,
                id=build_input_document(document),
                unsave=bool(unsave),
            ),
            timeout=timeout,
        )

    async def clear(self, *, attached: bool = False, timeout: float = 20.0) -> Any:
        flags = 1 if attached else 0
        return await self._raw.invoke_api(
            MessagesClearRecentStickers(flags=flags, attached=True if attached else None),
            timeout=timeout,
        )


class StickerFavoritesAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def list(self, *, hash: int = 0, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(MessagesGetFavedStickers(hash=int(hash)), timeout=timeout)

    async def set(
        self,
        document: DocumentRef | Any,
        *,
        unfave: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            MessagesFaveSticker(id=build_input_document(document), unfave=bool(unfave)),
            timeout=timeout,
        )


class StickerEmojiAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def custom_docs(self, document_ids: Sequence[int], *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            MessagesGetCustomEmojiDocuments(document_id=[int(x) for x in document_ids]),
            timeout=timeout,
        )


class StickersAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw
        self.sets = StickerSetsAPI(raw)
        self.search = StickerSearchAPI(raw)
        self.recent = StickerRecentAPI(raw)
        self.favorites = StickerFavoritesAPI(raw)
        self.emoji = StickerEmojiAPI(raw)
