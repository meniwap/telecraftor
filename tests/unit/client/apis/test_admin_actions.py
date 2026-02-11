from __future__ import annotations

import asyncio
from typing import Any

from telecraft.client.admin import ADMIN_RIGHTS_BASIC, banned_rights_full_ban
from telecraft.client.mtproto import ClientInit, MtprotoClient


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


# ===================== High-level convenience method tests =====================


def test_ban_user_uses_edit_banned_with_view_messages_true() -> None:
    """ban_user should call edit_banned with view_messages=True (full ban)."""
    c = _make_connected_client()

    c.entities.channel_access_hash[100] = 555
    c.entities.user_access_hash[200] = 777

    seen: list[Any] = []

    async def invoke_api(req: Any, *, timeout: float = 0) -> Any:
        seen.append(req)
        return type("_U", (), {"users": [], "chats": []})()

    c.invoke_api = invoke_api  # type: ignore[assignment]

    res = asyncio.run(c.ban_user(("channel", 100), ("user", 200), until_date=0))
    assert res is not None
    assert len(seen) == 1
    req = seen[0]
    assert getattr(req, "TL_NAME", None) == "channels.editBanned"
    rights = getattr(req, "banned_rights", None)
    assert rights is not None
    # view_messages=True means fully banned
    assert getattr(rights, "view_messages", None) is True


def test_unban_user_uses_edit_banned_with_all_false() -> None:
    """unban_user should call edit_banned with all rights False."""
    c = _make_connected_client()

    c.entities.channel_access_hash[100] = 555
    c.entities.user_access_hash[200] = 777

    seen: list[Any] = []

    async def invoke_api(req: Any, *, timeout: float = 0) -> Any:
        seen.append(req)
        return type("_U", (), {"users": [], "chats": []})()

    c.invoke_api = invoke_api  # type: ignore[assignment]

    res = asyncio.run(c.unban_user(("channel", 100), ("user", 200)))
    assert res is not None
    assert len(seen) == 1
    req = seen[0]
    assert getattr(req, "TL_NAME", None) == "channels.editBanned"
    rights = getattr(req, "banned_rights", None)
    assert rights is not None
    # All rights should be False (no restrictions)
    assert getattr(rights, "view_messages", None) is False
    assert getattr(rights, "send_messages", None) is False


def test_kick_user_calls_ban_then_unban() -> None:
    """kick_user should first ban, then immediately unban."""
    c = _make_connected_client()

    c.entities.channel_access_hash[100] = 555
    c.entities.user_access_hash[200] = 777

    seen: list[Any] = []

    async def invoke_api(req: Any, *, timeout: float = 0) -> Any:
        seen.append(req)
        return type("_U", (), {"users": [], "chats": []})()

    c.invoke_api = invoke_api  # type: ignore[assignment]

    res = asyncio.run(c.kick_user(("channel", 100), ("user", 200)))
    assert res is not None
    # Should have 2 calls: ban then unban
    assert len(seen) == 2
    # First call: ban (view_messages=True)
    assert getattr(seen[0], "TL_NAME", None) == "channels.editBanned"
    assert getattr(getattr(seen[0], "banned_rights", None), "view_messages", None) is True
    # Second call: unban (view_messages=False)
    assert getattr(seen[1], "TL_NAME", None) == "channels.editBanned"
    assert getattr(getattr(seen[1], "banned_rights", None), "view_messages", None) is False


def test_promote_admin_uses_edit_admin_with_rights() -> None:
    """promote_admin should call edit_admin with specified rights."""
    c = _make_connected_client()

    c.entities.channel_access_hash[100] = 555
    c.entities.user_access_hash[200] = 777

    seen: list[Any] = []

    async def invoke_api(req: Any, *, timeout: float = 0) -> Any:
        seen.append(req)
        return type("_U", (), {"users": [], "chats": []})()

    c.invoke_api = invoke_api  # type: ignore[assignment]

    res = asyncio.run(
        c.promote_admin(
            ("channel", 100),
            ("user", 200),
            delete_messages=True,
            ban_users=True,
            rank="Moderator",
        )
    )
    assert res is not None
    assert len(seen) == 1
    req = seen[0]
    assert getattr(req, "TL_NAME", None) == "channels.editAdmin"
    assert getattr(req, "rank", None) == "Moderator"
    rights = getattr(req, "admin_rights", None)
    assert rights is not None
    assert getattr(rights, "delete_messages", None) is True
    assert getattr(rights, "ban_users", None) is True


def test_demote_admin_uses_edit_admin_with_no_rights() -> None:
    """demote_admin should call edit_admin with all rights False."""
    c = _make_connected_client()

    c.entities.channel_access_hash[100] = 555
    c.entities.user_access_hash[200] = 777

    seen: list[Any] = []

    async def invoke_api(req: Any, *, timeout: float = 0) -> Any:
        seen.append(req)
        return type("_U", (), {"users": [], "chats": []})()

    c.invoke_api = invoke_api  # type: ignore[assignment]

    res = asyncio.run(c.demote_admin(("channel", 100), ("user", 200)))
    assert res is not None
    assert len(seen) == 1
    req = seen[0]
    assert getattr(req, "TL_NAME", None) == "channels.editAdmin"
    assert getattr(req, "rank", None) == ""
    rights = getattr(req, "admin_rights", None)
    assert rights is not None
    # All rights should be False
    assert getattr(rights, "change_info", None) is False
    assert getattr(rights, "delete_messages", None) is False
    assert getattr(rights, "ban_users", None) is False


def test_get_chat_member_calls_channels_get_participant() -> None:
    """get_chat_member should call channels.getParticipant."""
    c = _make_connected_client()

    c.entities.channel_access_hash[100] = 555
    c.entities.user_access_hash[200] = 777

    seen: list[Any] = []

    async def invoke_api(req: Any, *, timeout: float = 0) -> Any:
        seen.append(req)
        return type(
            "_P",
            (),
            {
                "users": [],
                "chats": [],
                "participant": type("_Part", (), {"TL_NAME": "channelParticipant"})(),
            },
        )()

    c.invoke_api = invoke_api  # type: ignore[assignment]

    res = asyncio.run(c.get_chat_member(("channel", 100), ("user", 200)))
    assert res is not None
    assert len(seen) == 1
    req = seen[0]
    assert getattr(req, "TL_NAME", None) == "channels.getParticipant"
