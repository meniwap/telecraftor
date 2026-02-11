from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from telecraft.client.mtproto import ClientInit, MtprotoClient
from telecraft.client.peers import Peer
from telecraft.tl.generated.types import InputPeerSelf


def test_send_file_routes_to_send_media_photo(tmp_path: Path) -> None:
    p = tmp_path / "a.jpg"
    p.write_bytes(b"\x00" * 123)

    client = MtprotoClient(network="test", dc_id=2, init=ClientInit(api_id=1, api_hash="x"))
    # Pretend connected.
    client._transport = object()  # type: ignore[attr-defined]
    client._sender = object()  # type: ignore[attr-defined]
    client._state = object()  # type: ignore[attr-defined]

    async def resolve_peer(_ref: Any, *, timeout: float = 0) -> Peer:
        return Peer.user(1)

    async def invoke_api(req: Any, *, timeout: float = 0) -> Any:
        # upload.save* returns Bool, sendMedia returns Updates; we don't care here.
        seen.append(req)
        return True

    seen: list[Any] = []
    client.resolve_peer = resolve_peer  # type: ignore[assignment]
    client.entities = type("_E", (), {"input_peer": staticmethod(lambda _p: InputPeerSelf())})()  # type: ignore[assignment]
    client.invoke_api = invoke_api  # type: ignore[assignment]

    asyncio.run(client.send_file("@x", p, caption="hi", as_photo=True))

    assert any(getattr(x, "TL_NAME", None) == "messages.sendMedia" for x in seen)
    send_req = [x for x in seen if getattr(x, "TL_NAME", None) == "messages.sendMedia"][-1]
    media = getattr(send_req, "media", None)
    assert getattr(media, "TL_NAME", None) == "inputMediaUploadedPhoto"
    assert getattr(send_req, "message", None) == "hi"


def test_send_file_routes_to_send_media_document(tmp_path: Path) -> None:
    p = tmp_path / "a.txt"
    p.write_text("hello")

    client = MtprotoClient(network="test", dc_id=2, init=ClientInit(api_id=1, api_hash="x"))
    # Pretend connected.
    client._transport = object()  # type: ignore[attr-defined]
    client._sender = object()  # type: ignore[attr-defined]
    client._state = object()  # type: ignore[attr-defined]

    async def resolve_peer(_ref: Any, *, timeout: float = 0) -> Peer:
        return Peer.user(1)

    seen: list[Any] = []

    async def invoke_api(req: Any, *, timeout: float = 0) -> Any:
        seen.append(req)
        return True

    client.resolve_peer = resolve_peer  # type: ignore[assignment]
    client.entities = type("_E", (), {"input_peer": staticmethod(lambda _p: InputPeerSelf())})()  # type: ignore[assignment]
    client.invoke_api = invoke_api  # type: ignore[assignment]

    asyncio.run(client.send_file("@x", p, caption=None, as_photo=False))

    send_req = [x for x in seen if getattr(x, "TL_NAME", None) == "messages.sendMedia"][-1]
    media = getattr(send_req, "media", None)
    assert getattr(media, "TL_NAME", None) == "inputMediaUploadedDocument"
