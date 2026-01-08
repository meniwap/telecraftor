from __future__ import annotations

import hashlib
import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path
from secrets import randbits
from typing import Any, Callable, Literal

from telecraft.tl.generated.functions import UploadGetFile, UploadSaveBigFilePart, UploadSaveFilePart
from telecraft.tl.generated.types import (
    InputDocumentFileLocation,
    InputFile,
    InputFileBig,
    InputPhotoFileLocation,
    UploadFile,
    UploadFileCdnRedirect,
)

PART_SIZE = 512 * 1024
BIG_FILE_THRESHOLD = 10 * 1024 * 1024  # Telegram threshold for InputFileBig flow.


class MediaError(Exception):
    pass


def _tl_bool(v: object) -> bool | None:
    """
    Our codec represents TL Bool in two possible ways:
    - python bool (True/False) in some paths
    - TL objects BoolTrue()/BoolFalse() (generated types)
    """
    if v is True:
        return True
    if v is False:
        return False
    name = getattr(v, "TL_NAME", None)
    if name == "boolTrue" or name == "true":
        return True
    if name == "boolFalse":
        return False
    tl_id = getattr(v, "TL_ID", None)
    if tl_id == -1720552011:  # boolTrue
        return True
    if tl_id == -1132882121:  # boolFalse
        return False
    return None


@dataclass(slots=True)
class ExtractedMedia:
    kind: Literal["photo", "document"]
    dc_id: int
    location: Any  # InputFileLocation
    file_name: str
    size: int | None = None


def _decode_text(v: object) -> str | None:
    if v is None:
        return None
    if isinstance(v, str):
        return v
    if isinstance(v, (bytes, bytearray)):
        return bytes(v).decode("utf-8", "replace")
    return str(v)


def _unwrap_message_like(obj: Any) -> Any:
    """
    Accept:
    - telecraft.bot.events.MessageEvent (has .raw)
    - TL update wrappers (have .message)
    - TL message objects
    """
    if obj is None:
        return None
    raw = getattr(obj, "raw", None)
    if raw is not None:
        obj = raw
    name = getattr(obj, "TL_NAME", None)
    if name in {
        "updateNewMessage",
        "updateNewChannelMessage",
        "updateEditMessage",
        "updateEditChannelMessage",
    }:
        inner = getattr(obj, "message", None)
        if inner is not None:
            obj = inner
    return obj


@dataclass(slots=True)
class PhotoSizeInfo:
    """Information about a photo size for download."""

    type: str  # The size type string (e.g. "y", "x", "m", "s")
    width: int | None
    height: int | None
    size: int | None
    cached_bytes: bytes | None  # For photoCachedSize, we have the bytes directly


def _get_photo_sizes_info(photo: Any) -> list[PhotoSizeInfo]:
    """
    Extract all downloadable photo size information.

    Handles:
    - photoSize: has type, w, h, size
    - photoCachedSize: has type, w, h, bytes (inline data!)
    - photoSizeProgressive: has type, w, h, sizes (list of progressive sizes)
    """
    sizes = getattr(photo, "sizes", None)
    if not isinstance(sizes, list) or not sizes:
        return []

    result: list[PhotoSizeInfo] = []

    for s in sizes:
        t = _decode_text(getattr(s, "type", None))
        if not t:
            continue

        name = getattr(s, "TL_NAME", None)

        # Skip non-downloadable pseudo sizes
        if t in {"i"}:  # Inline stripped preview
            continue
        if name in {"photoStrippedSize", "photoPathSize"}:
            continue

        w = getattr(s, "w", None)
        h = getattr(s, "h", None)
        width = int(w) if isinstance(w, int) else None
        height = int(h) if isinstance(h, int) else None

        # Check for cached bytes (photoCachedSize)
        cached_b = getattr(s, "bytes", None)
        cached_bytes = bytes(cached_b) if isinstance(cached_b, (bytes, bytearray)) else None

        # Determine size
        if name == "photoCachedSize" and cached_bytes:
            size = len(cached_bytes)
        elif name == "photoSizeProgressive":
            # Progressive sizes are stored in .sizes list
            prog_sizes = getattr(s, "sizes", None)
            if isinstance(prog_sizes, list) and prog_sizes:
                size = int(prog_sizes[-1])  # Last (largest) size
            else:
                size = None
        else:
            sz = getattr(s, "size", None)
            size = int(sz) if isinstance(sz, int) else None

        result.append(PhotoSizeInfo(
            type=t,
            width=width,
            height=height,
            size=size,
            cached_bytes=cached_bytes,
        ))

    return result


def _pick_best_photo_size(photo: Any) -> PhotoSizeInfo | None:
    """
    Pick the best (largest) photo size for download.

    Returns PhotoSizeInfo with type and optional cached_bytes.
    """
    sizes = _get_photo_sizes_info(photo)
    if not sizes:
        return None

    # Score by area (w*h) or size in bytes
    def score(s: PhotoSizeInfo) -> int:
        if s.width and s.height:
            return s.width * s.height
        if s.size:
            return s.size
        return 0

    return max(sizes, key=score)


def _pick_best_photo_size_type(photo: Any) -> str | None:
    """
    Pick the best photo size type string for InputPhotoFileLocation.thumb_size.

    This is a convenience wrapper for backward compatibility.
    """
    best = _pick_best_photo_size(photo)
    return best.type if best else None


@dataclass(slots=True)
class ExtractedMediaWithCache(ExtractedMedia):
    """ExtractedMedia that may include cached bytes for small photos."""

    cached_bytes: bytes | None = None


def extract_media(message_or_event: Any) -> ExtractedMedia | None:
    msg = _unwrap_message_like(message_or_event)
    if msg is None:
        return None

    media = getattr(msg, "media", None)
    if media is None:
        return None

    mname = getattr(media, "TL_NAME", None)

    if mname == "messageMediaPhoto":
        photo = getattr(media, "photo", None)
        if photo is None or getattr(photo, "TL_NAME", None) != "photo":
            return None

        dc_id = getattr(photo, "dc_id", None)
        if not isinstance(dc_id, int):
            return None

        best_size = _pick_best_photo_size(photo)
        if not best_size:
            return None

        loc = InputPhotoFileLocation(
            id=int(getattr(photo, "id")),
            access_hash=int(getattr(photo, "access_hash")),
            file_reference=bytes(getattr(photo, "file_reference", b"") or b""),
            thumb_size=best_size.type,
        )
        fname = f"photo_{int(getattr(photo, 'id'))}.jpg"

        # For cached photos, include the bytes directly
        if best_size.cached_bytes:
            return ExtractedMediaWithCache(
                kind="photo",
                dc_id=int(dc_id),
                location=loc,
                file_name=fname,
                size=len(best_size.cached_bytes),
                cached_bytes=best_size.cached_bytes,
            )

        return ExtractedMedia(
            kind="photo",
            dc_id=int(dc_id),
            location=loc,
            file_name=fname,
            size=best_size.size,
        )

    if mname == "messageMediaDocument":
        doc = getattr(media, "document", None)
        if doc is None or getattr(doc, "TL_NAME", None) != "document":
            return None

        dc_id = getattr(doc, "dc_id", None)
        if not isinstance(dc_id, int):
            return None

        loc = InputDocumentFileLocation(
            id=int(getattr(doc, "id")),
            access_hash=int(getattr(doc, "access_hash")),
            file_reference=bytes(getattr(doc, "file_reference", b"") or b""),
            thumb_size="",
        )

        fname: str | None = None
        attrs = getattr(doc, "attributes", None)
        if isinstance(attrs, list):
            for a in attrs:
                if getattr(a, "TL_NAME", None) == "documentAttributeFilename":
                    fname = _decode_text(getattr(a, "file_name", None))
                    break
        if not fname:
            # Best-effort from mime type.
            mime = _decode_text(getattr(doc, "mime_type", None)) or "application/octet-stream"
            ext = mimetypes.guess_extension(mime) or ""
            fname = f"document_{int(getattr(doc, 'id'))}{ext}"

        size_v = getattr(doc, "size", None)
        size = int(size_v) if isinstance(size_v, int) else None
        return ExtractedMedia(
            kind="document",
            dc_id=int(dc_id),
            location=loc,
            file_name=str(fname),
            size=size,
        )

    return None


async def upload_file(
    path: str | Path,
    *,
    invoke_api: Callable[..., Any],
    timeout: float,
    part_size: int = PART_SIZE,
    file_id: int | None = None,
    big_file_threshold: int = BIG_FILE_THRESHOLD,
) -> InputFile | InputFileBig:
    p = Path(path)
    if not p.exists() or not p.is_file():
        raise MediaError(f"upload_file: not a file: {p}")

    st = p.stat()
    file_size = int(st.st_size)
    parts = (file_size + part_size - 1) // part_size
    fid = int(file_id) if file_id is not None else randbits(63)

    use_big = file_size >= int(big_file_threshold)
    md5 = hashlib.md5() if not use_big else None  # noqa: S324 (telegram requires md5 for small)

    with p.open("rb") as f:
        part = 0
        while True:
            chunk = f.read(part_size)
            if not chunk:
                break
            if md5 is not None:
                md5.update(chunk)

            if use_big:
                req = UploadSaveBigFilePart(
                    file_id=fid,
                    file_part=int(part),
                    file_total_parts=int(parts),
                    bytes=chunk,
                )
            else:
                req = UploadSaveFilePart(file_id=fid, file_part=int(part), bytes=chunk)

            ok = await invoke_api(req, timeout=timeout)
            ok_b = _tl_bool(ok)
            if ok_b is not True:
                raise MediaError(
                    f"upload_file: upload part failed (part={part}, ok={ok!r})"
                )
            part += 1

    if part != parts:
        raise MediaError(f"upload_file: read parts mismatch: expected={parts} got={part}")

    name = p.name
    if use_big:
        return InputFileBig(id=fid, parts=int(parts), name=name)
    return InputFile(id=fid, parts=int(parts), name=name, md5_checksum=md5.hexdigest() if md5 else "")


def guess_mime_type(path: str | Path) -> str:
    p = str(path)
    mt, _enc = mimetypes.guess_type(p)
    return mt or "application/octet-stream"


def default_as_photo(path: str | Path) -> bool:
    """
    Product-y heuristic: treat common still images as photos; everything else as document.
    """
    p = Path(path)
    ext = p.suffix.lower()
    if ext in {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}:
        return True
    # Fallback by mime type, excluding known non-photo image containers.
    mime = guess_mime_type(p)
    if mime.startswith("image/") and ext not in {".gif", ".webp"}:
        return True
    return False


async def download_via_get_file(
    *,
    invoke_api: Callable[..., Any],
    location: Any,
    timeout: float,
    limit: int = PART_SIZE,
    expected_size: int | None = None,
) -> bytes:
    out = bytearray()
    offset = 0
    while True:
        res = await invoke_api(
            UploadGetFile(
                flags=0,
                precise=False,
                cdn_supported=False,
                location=location,
                offset=int(offset),
                limit=int(limit),
            ),
            timeout=timeout,
        )

        if isinstance(res, UploadFileCdnRedirect):
            raise MediaError("download_media: CDN redirect not supported in MVP")
        if not isinstance(res, UploadFile):
            raise MediaError(f"download_media: unexpected upload.getFile result: {type(res).__name__}")

        b = getattr(res, "bytes", None)
        if not isinstance(b, (bytes, bytearray)):
            raise MediaError("download_media: upload.file.bytes missing/invalid")

        chunk = bytes(b)
        if not chunk:
            break
        out += chunk
        offset += len(chunk)

        if expected_size is not None and offset >= int(expected_size):
            break
        if len(chunk) < int(limit):
            break

        # Extra safety: avoid unbounded growth on malformed responses.
        if expected_size is None and offset > 512 * 1024 * 1024:
            raise MediaError("download_media: exceeded 512MiB without a known size")

    return bytes(out)


def ensure_dest_path(dest: str | Path, *, file_name: str) -> Path:
    d = Path(dest)
    # If dest is a directory (or ends with path separator), create file inside it.
    if d.exists() and d.is_dir():
        return d / file_name
    if str(dest).endswith(os.sep):
        return d / file_name
    return d


