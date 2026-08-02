from __future__ import annotations

from dataclasses import dataclass

from .base import MAX_FRAME_SIZE_BYTES, TransportError


@dataclass(frozen=True, slots=True)
class AbridgedFraming:
    """
    MTProto transport: abridged.

    On connect, client must send 0xef.

    Frame format:
    - length in 4-byte words (payload_len / 4)
    - if length < 127: one byte length
      else: 0x7f + 3 bytes little-endian length
    - followed by payload bytes
    """

    CONNECT_HEADER: bytes = b"\xef"

    def encode(self, payload: bytes) -> bytes:
        if len(payload) % 4 != 0:
            raise TransportError("Abridged framing requires payload length multiple of 4 bytes.")
        if len(payload) > MAX_FRAME_SIZE_BYTES:
            raise TransportError("Payload too large for abridged framing.")

        ln_words = len(payload) // 4
        if ln_words < 127:
            return bytes([ln_words]) + payload
        if ln_words >= 1 << 24:
            raise TransportError("Payload too large for abridged framing.")
        return b"\x7f" + ln_words.to_bytes(3, "little") + payload

    def decode_from_buffer(self, buffer: bytearray) -> bytes | None:
        if not buffer:
            return None
        first = buffer[0]
        if first == 0x7F:
            if len(buffer) < 4:
                return None
            ln_words = int.from_bytes(buffer[1:4], "little")
            header_len = 4
        else:
            ln_words = first
            header_len = 1
        payload_len = ln_words * 4
        if payload_len > MAX_FRAME_SIZE_BYTES:
            raise TransportError(
                f"Abridged payload exceeds maximum frame size: {payload_len} > "
                f"{MAX_FRAME_SIZE_BYTES}"
            )
        total = header_len + payload_len
        if len(buffer) < total:
            return None
        payload = bytes(buffer[header_len:total])
        del buffer[:total]
        return payload
