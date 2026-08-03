from __future__ import annotations

import asyncio
import struct

import pytest

from telecraft.mtproto.transport.abridged import AbridgedFraming
from telecraft.mtproto.transport.base import MAX_FRAME_SIZE_BYTES, Endpoint, TransportError
from telecraft.mtproto.transport.intermediate import IntermediateFraming
from telecraft.mtproto.transport.tcp import TcpTransport


def test_abridged_encode_decode_small() -> None:
    f = AbridgedFraming()
    payload = b"\x01\x02\x03\x04" * 3  # 12 bytes => 3 words
    framed = f.encode(payload)
    assert framed[:1] == b"\x03"
    buf = bytearray(framed)
    out = f.decode_from_buffer(buf)
    assert out == payload
    assert buf == bytearray()


def test_abridged_encode_decode_large_header() -> None:
    f = AbridgedFraming()
    payload = b"\x00\x00\x00\x00" * 200  # 200 words => uses 0x7f + 3 bytes
    framed = f.encode(payload)
    assert framed[0] == 0x7F
    buf = bytearray(framed)
    out = f.decode_from_buffer(buf)
    assert out == payload
    assert buf == bytearray()


def test_abridged_requires_multiple_of_4() -> None:
    f = AbridgedFraming()
    with pytest.raises(Exception):
        f.encode(b"\x00")


def test_intermediate_encode_decode() -> None:
    f = IntermediateFraming()
    payload = b"\xaa\xbb\xcc\xdd" * 5
    framed = f.encode(payload)
    buf = bytearray(framed)
    out = f.decode_from_buffer(buf)
    assert out == payload
    assert buf == bytearray()


def test_intermediate_partial_buffer() -> None:
    f = IntermediateFraming()
    payload = b"\xaa\xbb\xcc\xdd" * 2
    framed = f.encode(payload)
    buf = bytearray(framed[:3])
    assert f.decode_from_buffer(buf) is None
    buf.extend(framed[3:])
    assert f.decode_from_buffer(buf) == payload


def test_intermediate_rejects_oversized_advertised_length_from_header() -> None:
    f = IntermediateFraming()
    buf = bytearray(struct.pack("<i", MAX_FRAME_SIZE_BYTES + 4))

    with pytest.raises(TransportError, match="maximum frame size"):
        f.decode_from_buffer(buf)


def test_abridged_rejects_oversized_advertised_length_from_header() -> None:
    f = AbridgedFraming()
    words = (MAX_FRAME_SIZE_BYTES // 4) + 1
    buf = bytearray(b"\x7f" + words.to_bytes(3, "little"))

    with pytest.raises(TransportError, match="maximum frame size"):
        f.decode_from_buffer(buf)


class _NeverCompletesFraming:
    def encode(self, payload: bytes) -> bytes:
        return payload

    def decode_from_buffer(self, buffer: bytearray) -> bytes | None:
        return None


class _ChunkReader:
    async def read(self, _size: int) -> bytes:
        return b"x" * 8


def test_tcp_transport_bounds_buffer_for_custom_framing(monkeypatch) -> None:
    from telecraft.mtproto.transport import tcp

    monkeypatch.setattr(tcp, "MAX_FRAME_SIZE_BYTES", 8)
    transport = TcpTransport(
        endpoint=Endpoint("127.0.0.1", 443),
        framing=_NeverCompletesFraming(),
    )
    transport._reader = _ChunkReader()  # type: ignore[assignment]

    with pytest.raises(TransportError, match="Receive buffer exceeded"):
        asyncio.run(transport.recv())
