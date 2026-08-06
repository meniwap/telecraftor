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


class _FailingWriter:
    def __init__(self) -> None:
        self.closed = False
        self.written: list[bytes] = []

    def write(self, payload: bytes) -> None:
        self.written.append(payload)

    async def drain(self) -> None:
        raise TimeoutError("socket stayed blocked")

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        return None


class _SlowClosingWriter:
    def __init__(self) -> None:
        self.drain_started = asyncio.Event()
        self.wait_closed_started = asyncio.Event()
        self.release_close = asyncio.Event()
        self.closed = False

    def write(self, _payload: bytes) -> None:
        return None

    async def drain(self) -> None:
        self.drain_started.set()
        await asyncio.Future()

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        self.wait_closed_started.set()
        await self.release_close.wait()


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


def test_tcp_transport_closes_after_failed_frame_write() -> None:
    transport = TcpTransport(
        endpoint=Endpoint("127.0.0.1", 443),
        framing=IntermediateFraming(),
    )
    writer = _FailingWriter()
    transport._writer = writer  # type: ignore[assignment]

    with pytest.raises(TransportError, match="writing MTProto frame"):
        asyncio.run(transport.send(b"\x00" * 4))

    assert writer.closed is True
    assert transport._writer is None


def test_tcp_transport_send_cancellation_detaches_writer_before_wait_closed() -> None:
    async def run() -> None:
        transport = TcpTransport(
            endpoint=Endpoint("127.0.0.1", 443),
            framing=IntermediateFraming(),
            close_timeout=0.02,
        )
        writer = _SlowClosingWriter()
        transport._writer = writer  # type: ignore[assignment]
        transport._reader = object()  # type: ignore[assignment]
        transport._rx_buf.extend(b"buffered")

        send_task = asyncio.create_task(transport.send(b"\x00" * 4))
        await asyncio.wait_for(writer.drain_started.wait(), timeout=0.1)
        send_task.cancel()
        try:
            await asyncio.wait_for(writer.wait_closed_started.wait(), timeout=0.1)
            await asyncio.sleep(0.05)

            assert writer.closed is True
            assert transport._writer is None
            assert transport._reader is None
            assert transport._rx_buf == bytearray()
            assert send_task.done() is True
            assert len(transport._close_wait_tasks) == 1
            with pytest.raises(asyncio.CancelledError):
                await send_task
        finally:
            writer.release_close.set()
            await asyncio.wait_for(
                asyncio.gather(*transport._close_wait_tasks),
                timeout=0.1,
            )

    asyncio.run(run())
