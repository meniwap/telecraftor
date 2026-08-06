from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from .base import MAX_FRAME_SIZE_BYTES, Endpoint, Framing, TransportError

_MAX_FRAMING_HEADER_SIZE = 4


@dataclass(slots=True)
class TcpTransport:
    endpoint: Endpoint
    framing: Framing
    connect_timeout: float = 10.0
    write_timeout: float = 20.0
    close_timeout: float = 5.0

    _reader: asyncio.StreamReader | None = None
    _writer: asyncio.StreamWriter | None = None
    _rx_buf: bytearray = field(default_factory=bytearray)
    _close_wait_tasks: set[asyncio.Task[None]] = field(
        default_factory=set,
        init=False,
        repr=False,
    )

    async def connect(self) -> None:
        if self._writer is not None:
            return
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.endpoint.host, self.endpoint.port),
                timeout=self.connect_timeout,
            )
            self._reader, self._writer = reader, writer
        except Exception as e:  # noqa: BLE001
            raise TransportError(f"Failed to connect to {self.endpoint}") from e

        # Some MTProto transport variants require a connection header.
        header = getattr(self.framing, "CONNECT_HEADER", b"")
        if header:
            if not isinstance(header, (bytes, bytearray)):
                await self.close()
                raise TransportError("Framing CONNECT_HEADER must be bytes")
            writer.write(bytes(header))
            try:
                await asyncio.wait_for(writer.drain(), timeout=self.write_timeout)
            except asyncio.CancelledError:
                await self.close()
                raise
            except Exception as e:  # noqa: BLE001
                await self.close()
                raise TransportError("Timed out writing MTProto connection header") from e

    def _detach_and_close_writer(self) -> asyncio.StreamWriter | None:
        """Synchronously make the transport unusable before graceful cleanup awaits."""

        writer = self._writer
        self._writer = None
        self._reader = None
        self._rx_buf.clear()
        if writer is not None:
            writer.close()
        return writer

    async def _wait_writer_closed(self, writer: asyncio.StreamWriter) -> None:
        wait_task = asyncio.create_task(
            writer.wait_closed(),
            name="telecraft:tcp-wait-closed",
        )
        self._close_wait_tasks.add(wait_task)

        def completed(done: asyncio.Task[None]) -> None:
            self._close_wait_tasks.discard(done)
            if not done.cancelled():
                _ = done.exception()

        wait_task.add_done_callback(completed)
        done, _pending = await asyncio.wait(
            {wait_task},
            timeout=max(0.0, self.close_timeout),
        )
        if wait_task in done:
            try:
                wait_task.result()
            except BaseException:
                pass

    async def close(self) -> None:
        writer = self._detach_and_close_writer()
        if writer is not None:
            await self._wait_writer_closed(writer)

    async def send(self, payload: bytes) -> None:
        writer = self._writer
        if writer is None:
            raise TransportError("Not connected.")
        if len(payload) > MAX_FRAME_SIZE_BYTES:
            raise TransportError(
                f"Payload exceeds maximum frame size: {len(payload)} > {MAX_FRAME_SIZE_BYTES}"
            )
        framed = self.framing.encode(payload)
        writer.write(framed)
        try:
            await asyncio.wait_for(writer.drain(), timeout=self.write_timeout)
        except asyncio.CancelledError:
            # The frame may already be buffered.  Closing is the only way to
            # ensure a cancelled send cannot later escape and become an
            # untracked, potentially non-idempotent RPC.
            await self.close()
            raise
        except Exception as e:  # noqa: BLE001
            await self.close()
            raise TransportError("Timed out writing MTProto frame") from e

    async def recv(self) -> bytes:
        if self._reader is None:
            raise TransportError("Not connected.")
        while True:
            payload = self.framing.decode_from_buffer(self._rx_buf)
            if payload is not None:
                if len(payload) > MAX_FRAME_SIZE_BYTES:
                    raise TransportError(
                        f"Received payload exceeds maximum frame size: {len(payload)} > "
                        f"{MAX_FRAME_SIZE_BYTES}"
                    )
                return payload
            # The built-in framings reject an oversized advertised length as
            # soon as its header arrives.  This independent bound also protects
            # TcpTransport if a custom Framing implementation never consumes
            # its input.  It is checked after decode so a complete maximum-size
            # frame is accepted even if the socket read also included bytes from
            # the next frame.
            if len(self._rx_buf) > MAX_FRAME_SIZE_BYTES + _MAX_FRAMING_HEADER_SIZE:
                raise TransportError(
                    "Receive buffer exceeded maximum frame size without yielding a frame"
                )
            chunk = await self._reader.read(4096)
            if not chunk:
                raise TransportError("Connection closed.")
            self._rx_buf.extend(chunk)
