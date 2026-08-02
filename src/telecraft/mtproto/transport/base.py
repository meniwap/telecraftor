from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

# Telegram RPC payloads are normally far smaller than this (file transfers are
# split into parts).  Keeping one shared ceiling prevents a peer from making the
# client buffer the much larger lengths representable by the wire framings.
MAX_FRAME_SIZE_BYTES = 16 * 1024 * 1024


class TransportError(Exception):
    pass


class Framing(Protocol):
    """
    Transport framing is responsible only for:
    - turning raw MTProto packet bytes into framed bytes (encode)
    - reading framed bytes and extracting a raw packet (decode)
    """

    def encode(self, payload: bytes) -> bytes: ...
    def decode_from_buffer(self, buffer: bytearray) -> bytes | None: ...


@dataclass(frozen=True, slots=True)
class Endpoint:
    host: str
    port: int
