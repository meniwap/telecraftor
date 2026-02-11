from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

from telecraft.client.media import (
    ExtractedMediaWithCache,
    _get_photo_sizes_info,
    _pick_best_photo_size,
    download_via_get_file,
    extract_media,
)
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
    msg = SimpleNamespace(
        TL_NAME="message", media=SimpleNamespace(TL_NAME="messageMediaDocument", document=doc)
    )
    m = extract_media(msg)
    assert m is not None
    assert m.kind == "document"
    assert m.dc_id == 2
    assert m.file_name == "a.txt"
    assert getattr(m.location, "TL_NAME", None) == "inputDocumentFileLocation"
    assert m.location.thumb_size == ""


def test_get_photo_sizes_info_handles_photosize() -> None:
    """Test that photoSize type is correctly parsed."""
    photo = SimpleNamespace(
        TL_NAME="photo",
        sizes=[
            SimpleNamespace(TL_NAME="photoSize", type="s", w=100, h=100, size=5000),
            SimpleNamespace(TL_NAME="photoSize", type="m", w=320, h=320, size=20000),
            SimpleNamespace(TL_NAME="photoSize", type="x", w=800, h=800, size=80000),
        ],
    )
    sizes = _get_photo_sizes_info(photo)
    assert len(sizes) == 3
    assert sizes[0].type == "s"
    assert sizes[0].width == 100
    assert sizes[0].size == 5000
    assert sizes[2].type == "x"
    assert sizes[2].width == 800


def test_get_photo_sizes_info_handles_cached_size() -> None:
    """Test that photoCachedSize has its bytes extracted."""
    cached_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    photo = SimpleNamespace(
        TL_NAME="photo",
        sizes=[
            SimpleNamespace(TL_NAME="photoCachedSize", type="m", w=100, h=100, bytes=cached_data),
        ],
    )
    sizes = _get_photo_sizes_info(photo)
    assert len(sizes) == 1
    assert sizes[0].type == "m"
    assert sizes[0].cached_bytes == cached_data
    assert sizes[0].size == len(cached_data)


def test_get_photo_sizes_info_handles_progressive() -> None:
    """Test that photoSizeProgressive correctly reads the last size."""
    photo = SimpleNamespace(
        TL_NAME="photo",
        sizes=[
            SimpleNamespace(
                TL_NAME="photoSizeProgressive",
                type="y",
                w=1280,
                h=1280,
                sizes=[10000, 50000, 150000],
            ),
        ],
    )
    sizes = _get_photo_sizes_info(photo)
    assert len(sizes) == 1
    assert sizes[0].type == "y"
    assert sizes[0].size == 150000  # Last (largest) progressive size


def test_get_photo_sizes_info_skips_stripped() -> None:
    """Test that stripped/path sizes are skipped."""
    photo = SimpleNamespace(
        TL_NAME="photo",
        sizes=[
            SimpleNamespace(TL_NAME="photoStrippedSize", type="i", bytes=b"\x00" * 50),
            SimpleNamespace(TL_NAME="photoPathSize", type="j", bytes=b"<svg/>"),
            SimpleNamespace(TL_NAME="photoSize", type="m", w=320, h=320, size=20000),
        ],
    )
    sizes = _get_photo_sizes_info(photo)
    assert len(sizes) == 1
    assert sizes[0].type == "m"


def test_pick_best_photo_size_by_area() -> None:
    """Test that we pick the largest photo by area."""
    photo = SimpleNamespace(
        TL_NAME="photo",
        sizes=[
            SimpleNamespace(TL_NAME="photoSize", type="s", w=100, h=100, size=5000),
            SimpleNamespace(TL_NAME="photoSize", type="x", w=800, h=600, size=80000),
            SimpleNamespace(TL_NAME="photoSize", type="m", w=320, h=320, size=20000),
        ],
    )
    best = _pick_best_photo_size(photo)
    assert best is not None
    assert best.type == "x"  # 800*600 = 480000 > 320*320 = 102400


def test_extract_media_photo_with_cached_bytes() -> None:
    """Test that cached photo bytes are extracted."""
    cached_data = b"\xff\xd8\xff\xe0" + b"\x00" * 100  # JPEG header + padding
    photo = SimpleNamespace(
        TL_NAME="photo",
        id=12345,
        access_hash=67890,
        file_reference=b"ref",
        dc_id=2,
        sizes=[
            SimpleNamespace(TL_NAME="photoCachedSize", type="m", w=100, h=100, bytes=cached_data),
        ],
    )
    msg = SimpleNamespace(
        TL_NAME="message",
        media=SimpleNamespace(TL_NAME="messageMediaPhoto", photo=photo),
    )
    m = extract_media(msg)
    assert m is not None
    assert m.kind == "photo"
    assert isinstance(m, ExtractedMediaWithCache)
    assert m.cached_bytes == cached_data


def test_extract_media_photo_regular() -> None:
    """Test regular photo extraction without cached bytes."""
    photo = SimpleNamespace(
        TL_NAME="photo",
        id=12345,
        access_hash=67890,
        file_reference=b"ref",
        dc_id=2,
        sizes=[
            SimpleNamespace(TL_NAME="photoSize", type="y", w=1280, h=1280, size=150000),
        ],
    )
    msg = SimpleNamespace(
        TL_NAME="message",
        media=SimpleNamespace(TL_NAME="messageMediaPhoto", photo=photo),
    )
    m = extract_media(msg)
    assert m is not None
    assert m.kind == "photo"
    assert m.dc_id == 2
    assert m.location.thumb_size == "y"
    assert m.size == 150000
    # Should NOT be ExtractedMediaWithCache (no cached bytes)
    if isinstance(m, ExtractedMediaWithCache):
        assert m.cached_bytes is None
