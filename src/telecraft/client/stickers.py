from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from telecraft.tl.generated.types import (
    InputDocument,
    InputStickerSetAnimatedEmoji,
    InputStickerSetDice,
    InputStickerSetId,
    InputStickerSetPremiumGifts,
    InputStickerSetShortName,
)

StickerSetRefKind = Literal["short_name", "id", "animated_emoji", "dice", "premium_gifts"]


@dataclass(frozen=True, slots=True)
class StickerSetRef:
    kind: StickerSetRefKind
    short_name_value: str | None = None
    set_id: int | None = None
    access_hash: int | None = None
    emoticon: str | None = None

    @classmethod
    def short_name(cls, short_name: str) -> StickerSetRef:
        value = str(short_name).strip()
        if not value:
            raise ValueError("short_name cannot be empty")
        return cls(kind="short_name", short_name_value=value)

    @classmethod
    def by_id(cls, set_id: int, access_hash: int) -> StickerSetRef:
        return cls(kind="id", set_id=int(set_id), access_hash=int(access_hash))

    @classmethod
    def animated_emoji(cls) -> StickerSetRef:
        return cls(kind="animated_emoji")

    @classmethod
    def dice(cls, emoticon: str) -> StickerSetRef:
        value = str(emoticon).strip()
        if not value:
            raise ValueError("emoticon cannot be empty")
        return cls(kind="dice", emoticon=value)

    @classmethod
    def premium_gifts(cls) -> StickerSetRef:
        return cls(kind="premium_gifts")


@dataclass(frozen=True, slots=True)
class DocumentRef:
    doc_id: int
    access_hash: int
    file_reference: bytes = b""

    @classmethod
    def from_parts(
        cls,
        doc_id: int,
        access_hash: int,
        file_reference: bytes = b"",
    ) -> DocumentRef:
        return cls(
            doc_id=int(doc_id),
            access_hash=int(access_hash),
            file_reference=bytes(file_reference),
        )


def build_input_sticker_set(ref: StickerSetRef | Any) -> Any:
    if not isinstance(ref, StickerSetRef):
        return ref
    if ref.kind == "short_name":
        if not ref.short_name_value:
            raise ValueError("StickerSetRef.short_name requires short_name")
        return InputStickerSetShortName(short_name=str(ref.short_name_value))
    if ref.kind == "id":
        if ref.set_id is None or ref.access_hash is None:
            raise ValueError("StickerSetRef.by_id requires set_id and access_hash")
        return InputStickerSetId(id=int(ref.set_id), access_hash=int(ref.access_hash))
    if ref.kind == "animated_emoji":
        return InputStickerSetAnimatedEmoji()
    if ref.kind == "dice":
        if not ref.emoticon:
            raise ValueError("StickerSetRef.dice requires emoticon")
        return InputStickerSetDice(emoticon=str(ref.emoticon))
    if ref.kind == "premium_gifts":
        return InputStickerSetPremiumGifts()
    raise ValueError(f"Unsupported StickerSetRef kind: {ref.kind!r}")


def build_input_document(document: DocumentRef | Any) -> Any:
    if not isinstance(document, DocumentRef):
        return document
    return InputDocument(
        id=int(document.doc_id),
        access_hash=int(document.access_hash),
        file_reference=bytes(document.file_reference),
    )
