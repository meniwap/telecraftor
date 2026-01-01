from __future__ import annotations

import asyncio
from typing import Any

from telecraft.client.admin import ADMIN_RIGHTS_BASIC, banned_rights_full_ban
from telecraft.client.mtproto import ClientInit, MtprotoClient
from telecraft.client.peers import Peer


def _make_connected_client() -> MtprotoClient:
    c = MtprotoClient(network="test", dc_id=2, init=ClientInit(api_id=1, api_hash="x"))
    # Pretend connected.
    c._transport = object()  # type: ignore[attr-defined]
    c._sender = object()  # type: ignore[attr-defined]
    c._state = object()  # type: ignore[attr-defined]
    return c


def test_edit_admin_builds_channels_edit_admin_request() -> None:
    c = _make_connected_client()

    # Seed access hashes required for InputChannel and InputUser.
    c.entities.channel_access_hash[100] = 555
    c.entities.user_access_hash[200] = 777

    seen: list[Any] = []

    async def invoke_api(req: Any, *, timeout: float = 0) -> Any:
        seen.append(req)
        # pretend Updates with users/chats fields
        return type("_U", (), {"users": [], "chats": []})()

    c.invoke_api = invoke_api  # type: ignore[assignment]

    res = asyncio.run(
        c.edit_admin(
            ("channel", 100),
            ("user", 200),
            admin_rights=ADMIN_RIGHTS_BASIC,
            rank="mod",
        )
    )
    assert res is not None
    assert len(seen) == 1
    req = seen[0]
    assert getattr(req, "TL_NAME", None) == "channels.editAdmin"
    assert getattr(getattr(req, "channel", None), "TL_NAME", None) == "inputChannel"
    assert getattr(getattr(req, "user_id", None), "TL_NAME", None) == "inputUser"
    assert getattr(getattr(req, "admin_rights", None), "TL_NAME", None) == "chatAdminRights"


def test_edit_banned_builds_channels_edit_banned_request() -> None:
    c = _make_connected_client()

    c.entities.channel_access_hash[100] = 555
    c.entities.user_access_hash[200] = 777

    seen: list[Any] = []

    async def invoke_api(req: Any, *, timeout: float = 0) -> Any:
        seen.append(req)
        return type("_U", (), {"users": [], "chats": []})()

    c.invoke_api = invoke_api  # type: ignore[assignment]

    rights = banned_rights_full_ban(until_date=0)
    res = asyncio.run(
        c.edit_banned(
            ("channel", 100),
            ("user", 200),
            banned_rights=rights,
        )
    )
    assert res is not None
    assert len(seen) == 1
    req = seen[0]
    assert getattr(req, "TL_NAME", None) == "channels.editBanned"
    assert getattr(getattr(req, "channel", None), "TL_NAME", None) == "inputChannel"
    # participant is InputPeerUser
    assert getattr(getattr(req, "participant", None), "TL_NAME", None) == "inputPeerUser"
    assert getattr(getattr(req, "banned_rights", None), "TL_NAME", None) == "chatBannedRights"


