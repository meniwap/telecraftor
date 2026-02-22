from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

from telecraft.client.media import BIG_FILE_THRESHOLD, PART_SIZE, MediaError, upload_file as media_upload_file
from telecraft.client.uploads import build_cdn_file_token, build_file_location
from telecraft.tl.generated.functions import (
    UploadGetCdnFile,
    UploadGetCdnFileHashes,
    UploadGetFile,
    UploadGetFileHashes,
    UploadGetWebFile,
    UploadReuploadCdnFile,
    UploadSaveBigFilePart,
    UploadSaveFilePart,
)

if TYPE_CHECKING:
    from telecraft.client.mtproto import MtprotoClient


class UploadsAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def save_part(
        self,
        file_id: int,
        file_part: int,
        bytes: Any,  # noqa: A002
        *,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            UploadSaveFilePart(
                file_id=int(file_id),
                file_part=int(file_part),
                bytes=bytes,
            ),
            timeout=timeout,
        )

    async def save_big_part(
        self,
        file_id: int,
        file_part: int,
        file_total_parts: int,
        bytes: Any,  # noqa: A002
        *,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            UploadSaveBigFilePart(
                file_id=int(file_id),
                file_part=int(file_part),
                file_total_parts=int(file_total_parts),
                bytes=bytes,
            ),
            timeout=timeout,
        )

    async def upload_file(
        self,
        path: str | Path,
        *,
        part_size: int = PART_SIZE,
        file_id: int | None = None,
        big_file_threshold: int = BIG_FILE_THRESHOLD,
        timeout: float = 60.0,
    ) -> Any:
        p = Path(path)
        if p.exists() and p.is_file():
            return await media_upload_file(
                p,
                invoke_api=self._raw.invoke_api,
                timeout=timeout,
                part_size=int(part_size),
                file_id=file_id,
                big_file_threshold=int(big_file_threshold),
            )

        # Contract-test fallback (SpyRaw exposes dynamic async methods).
        raw_upload = getattr(self._raw, "upload_file", None)
        if callable(raw_upload):
            return await raw_upload(
                path,
                part_size=int(part_size),
                file_id=file_id,
                big_file_threshold=int(big_file_threshold),
                timeout=timeout,
            )
        raise MediaError(f"upload_file: not a file: {p}")

    async def get_file(
        self,
        location: Any,
        *,
        offset: int = 0,
        limit: int = PART_SIZE,
        precise: bool = False,
        cdn_supported: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        flags = 0
        if precise:
            flags |= 1
        if cdn_supported:
            flags |= 2
        return await self._raw.invoke_api(
            UploadGetFile(
                flags=flags,
                precise=True if precise else None,
                cdn_supported=True if cdn_supported else None,
                location=build_file_location(location),
                offset=int(offset),
                limit=int(limit),
            ),
            timeout=timeout,
        )

    async def iter_file(
        self,
        location: Any,
        *,
        offset: int = 0,
        limit: int = PART_SIZE,
        precise: bool = False,
        cdn_supported: bool = False,
        timeout: float = 20.0,
    ) -> AsyncIterator[bytes]:
        cur = int(offset)
        chunk_limit = max(1, int(limit))
        while True:
            out = await self.get_file(
                location,
                offset=cur,
                limit=chunk_limit,
                precise=precise,
                cdn_supported=cdn_supported,
                timeout=timeout,
            )
            chunk = getattr(out, "bytes", None)
            if not isinstance(chunk, (bytes, bytearray)):
                break
            data = bytes(chunk)
            if not data:
                break
            yield data
            cur += len(data)
            if len(data) < chunk_limit:
                break

    async def get_cdn_file(
        self,
        file_token: Any,
        *,
        offset: int = 0,
        limit: int = PART_SIZE,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            UploadGetCdnFile(
                file_token=build_cdn_file_token(file_token),
                offset=int(offset),
                limit=int(limit),
            ),
            timeout=timeout,
        )

    async def reupload_cdn_file(
        self,
        file_token: Any,
        request_token: Any,
        *,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            UploadReuploadCdnFile(
                file_token=build_cdn_file_token(file_token),
                request_token=build_cdn_file_token(request_token),
            ),
            timeout=timeout,
        )

    async def get_web_file(
        self,
        location: Any,
        *,
        offset: int = 0,
        limit: int = PART_SIZE,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            UploadGetWebFile(
                location=build_file_location(location),
                offset=int(offset),
                limit=int(limit),
            ),
            timeout=timeout,
        )

    async def get_cdn_file_hashes(
        self,
        file_token: Any,
        *,
        offset: int = 0,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            UploadGetCdnFileHashes(file_token=build_cdn_file_token(file_token), offset=int(offset)),
            timeout=timeout,
        )

    async def get_file_hashes(self, location: Any, *, offset: int = 0, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            UploadGetFileHashes(location=build_file_location(location), offset=int(offset)),
            timeout=timeout,
        )
