from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any, Literal

from telecraft.tl.generated.types import (
    InputDocumentFileLocation,
    InputPhotoFileLocation,
    InputWebFileLocation,
)

FileLocationKind = Literal["raw", "document", "photo", "web"]


@dataclass(frozen=True, slots=True)
class FileLocationRef:
    kind: FileLocationKind
    location: Any = None
    id: int | None = None
    access_hash: int | None = None
    file_reference: bytes = b""
    thumb_size: str = ""
    url: str | None = None

    @classmethod
    def raw(cls, location: Any) -> FileLocationRef:
        return cls(kind="raw", location=location)

    @classmethod
    def document(
        cls,
        *,
        id: int,
        access_hash: int,
        file_reference: bytes = b"",
        thumb_size: str = "",
    ) -> FileLocationRef:
        return cls(
            kind="document",
            id=int(id),
            access_hash=int(access_hash),
            file_reference=bytes(file_reference),
            thumb_size=str(thumb_size),
        )

    @classmethod
    def photo(
        cls,
        *,
        id: int,
        access_hash: int,
        file_reference: bytes = b"",
        thumb_size: str = "",
    ) -> FileLocationRef:
        return cls(
            kind="photo",
            id=int(id),
            access_hash=int(access_hash),
            file_reference=bytes(file_reference),
            thumb_size=str(thumb_size),
        )

    @classmethod
    def web(cls, *, url: str, access_hash: int = 0) -> FileLocationRef:
        return cls(kind="web", url=str(url), access_hash=int(access_hash))


@dataclass(frozen=True, slots=True)
class CdnFileRef:
    file_token: bytes

    @classmethod
    def from_bytes(cls, file_token: bytes | bytearray) -> CdnFileRef:
        return cls(file_token=bytes(file_token))

    @classmethod
    def from_base64(cls, file_token_b64: str) -> CdnFileRef:
        raw = base64.b64decode(str(file_token_b64).encode("ascii"))
        return cls(file_token=bytes(raw))

    @classmethod
    def from_hex(cls, file_token_hex: str) -> CdnFileRef:
        return cls(file_token=bytes.fromhex(str(file_token_hex)))


def build_file_location(ref_or_location: FileLocationRef | Any) -> Any:
    if not isinstance(ref_or_location, FileLocationRef):
        return ref_or_location
    if ref_or_location.kind == "raw":
        return ref_or_location.location
    if ref_or_location.kind == "document":
        if ref_or_location.id is None or ref_or_location.access_hash is None:
            raise ValueError("FileLocationRef.document requires id and access_hash")
        return InputDocumentFileLocation(
            id=int(ref_or_location.id),
            access_hash=int(ref_or_location.access_hash),
            file_reference=bytes(ref_or_location.file_reference),
            thumb_size=str(ref_or_location.thumb_size),
        )
    if ref_or_location.kind == "photo":
        if ref_or_location.id is None or ref_or_location.access_hash is None:
            raise ValueError("FileLocationRef.photo requires id and access_hash")
        return InputPhotoFileLocation(
            id=int(ref_or_location.id),
            access_hash=int(ref_or_location.access_hash),
            file_reference=bytes(ref_or_location.file_reference),
            thumb_size=str(ref_or_location.thumb_size),
        )
    if ref_or_location.kind == "web":
        if ref_or_location.url is None:
            raise ValueError("FileLocationRef.web requires url")
        return InputWebFileLocation(
            url=str(ref_or_location.url),
            access_hash=int(ref_or_location.access_hash or 0),
        )
    raise ValueError(f"Unsupported FileLocationRef kind: {ref_or_location.kind!r}")


def build_cdn_file_token(token_or_ref: CdnFileRef | Any) -> Any:
    if isinstance(token_or_ref, CdnFileRef):
        return bytes(token_or_ref.file_token)
    if isinstance(token_or_ref, bytearray):
        return bytes(token_or_ref)
    if isinstance(token_or_ref, bytes):
        return token_or_ref
    if isinstance(token_or_ref, str):
        return token_or_ref.encode("utf-8")
    return token_or_ref
