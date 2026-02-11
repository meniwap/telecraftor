from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from typing import Any

from telecraft.client.media import PART_SIZE, upload_file
from telecraft.tl.generated.functions import UploadSaveBigFilePart, UploadSaveFilePart
from telecraft.tl.generated.types import InputFile, InputFileBig


def test_upload_file_small_uses_save_file_part_and_md5(tmp_path: Path) -> None:
    data = (b"abc123" * (PART_SIZE // 6)) + b"tail"
    p = tmp_path / "a.bin"
    p.write_bytes(data)

    seen: list[Any] = []

    async def invoke_api(req: Any, *, timeout: float) -> Any:
        seen.append(req)
        return True

    res = asyncio.run(
        upload_file(
            p,
            invoke_api=invoke_api,
            timeout=1.0,
            file_id=123,
            big_file_threshold=10 * 1024 * 1024,  # default, but explicit
        )
    )

    assert isinstance(res, InputFile)
    assert res.id == 123
    assert res.parts == 2
    assert res.name == "a.bin"
    assert res.md5_checksum == hashlib.md5(data).hexdigest()  # noqa: S324

    assert len(seen) == 2
    assert all(isinstance(x, UploadSaveFilePart) for x in seen)
    assert seen[0].file_part == 0
    assert seen[1].file_part == 1


def test_upload_file_big_uses_save_big_file_part(tmp_path: Path) -> None:
    # Just over 10MiB to force InputFileBig flow.
    data = b"x" * (10 * 1024 * 1024 + 1)
    p = tmp_path / "big.bin"
    p.write_bytes(data)

    seen: list[Any] = []

    async def invoke_api(req: Any, *, timeout: float) -> Any:
        seen.append(req)
        return True

    res = asyncio.run(upload_file(p, invoke_api=invoke_api, timeout=1.0, file_id=999))
    assert isinstance(res, InputFileBig)
    assert res.id == 999
    assert res.name == "big.bin"
    assert res.parts == (len(data) + PART_SIZE - 1) // PART_SIZE

    assert len(seen) == res.parts
    assert all(isinstance(x, UploadSaveBigFilePart) for x in seen)
    assert seen[0].file_part == 0
    assert seen[-1].file_part == res.parts - 1
    assert seen[0].file_total_parts == res.parts
