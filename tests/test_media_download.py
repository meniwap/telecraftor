from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

from telecraft.client.media import download_via_get_file, extract_media
from telecraft.tl.generated.types import (
    DocumentAttributeFilename,
    StorageFileUnknown,
    UploadFile,
)


def test_download_via_get_file_assembles_bytes() -> None:
    chunks = [b"abcd", b"efg", b""]
    calls: list[Any] = []

    async def invoke_api(req: Any, *, timeout: float) -> Any:
        calls.append(req)
        b = chunks.pop(0)
        return UploadFile(type=StorageFileUnknown(), mtime=0, bytes=b)

    data = asyncio.run(
        download_via_get_file(
            invoke_api=invoke_api,
            location=SimpleNamespace(TL_NAME="inputDocumentFileLocation"),
            timeout=1.0,
            limit=4,
        )
    )
    assert data == b"abcdefg"
    assert len(calls) == 2
    assert calls[0].offset == 0
    assert calls[1].offset == 4


def test_extract_media_document_builds_location_and_filename() -> None:
    doc = SimpleNamespace(
        TL_NAME="document",
        id=11,
        access_hash=22,
        file_reference=b"ref",
        dc_id=2,
        size=7,
        mime_type="text/plain",
        attributes=[DocumentAttributeFilename(file_name="a.txt")],
    )
    msg = SimpleNamespace(TL_NAME="message", media=SimpleNamespace(TL_NAME="messageMediaDocument", document=doc))
    m = extract_media(msg)
    assert m is not None
    assert m.kind == "document"
    assert m.dc_id == 2
    assert m.file_name == "a.txt"
    assert getattr(m.location, "TL_NAME", None) == "inputDocumentFileLocation"
    assert m.location.thumb_size == ""


