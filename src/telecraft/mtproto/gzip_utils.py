from __future__ import annotations

import gzip
import io

MAX_GZIP_UNPACKED_SIZE = 8 * 1024 * 1024


class GzipPayloadError(Exception):
    pass


def decompress_limited(
    data: bytes | bytearray,
    *,
    max_size: int = MAX_GZIP_UNPACKED_SIZE,
) -> bytes:
    if max_size < 0:
        raise GzipPayloadError("max_size must be non-negative")
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(bytes(data))) as gz:
            out = gz.read(max_size + 1)
    except Exception as e:  # noqa: BLE001
        raise GzipPayloadError("Invalid gzip payload") from e
    if len(out) > max_size:
        raise GzipPayloadError(f"gzip payload exceeds {max_size} unpacked bytes")
    return out
