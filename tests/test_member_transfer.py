"""Tests for member transfer and bulk operations."""
from __future__ import annotations

import asyncio
from typing import Any

from telecraft.client.mtproto import ClientInit, MtprotoClient


def _make_connected_client() -> MtprotoClient:
    c = MtprotoClient(network="test", dc_id=2, init=ClientInit(api_id=1, api_hash="x"))
    c._transport = object()  # type: ignore[attr-defined]
    c._sender = object()  # type: ignore[attr-defined]
    c._state = object()  # type: ignore[attr-defined]
    return c


# ===================== Add Users to Group Tests =====================


def test_add_users_to_group_returns_stats() -> None:
    """add_users_to_group should return success/failed stats."""
    c = _make_connected_client()
    c.entities.channel_access_hash[100] = 555
    c.entities.user_access_hash[1] = 111
    c.entities.user_access_hash[2] = 222
    c.entities.user_access_hash[3] = 333

    call_count = [0]

    async def invoke_api(req: Any, *, timeout: float = 0) -> Any:
        call_count[0] += 1
        # Simulate failure for user 2
        if call_count[0] == 2:
            from telecraft.mtproto.rpc.sender import RpcErrorException
            raise RpcErrorException(code=400, message="USER_PRIVACY_RESTRICTED")
        return type("_R", (), {"users": [], "chats": []})()

    c.invoke_api = invoke_api  # type: ignore[assignment]

    result = asyncio.run(c.add_users_to_group(
        ("channel", 100),
        [("user", 1), ("user", 2), ("user", 3)],
        on_error="skip",
    ))

    assert result["total"] == 3
    assert len(result["success"]) == 2
    assert len(result["failed"]) == 1


def test_add_users_to_group_raises_on_error() -> None:
    """add_users_to_group with on_error='raise' should raise on first error."""
    c = _make_connected_client()
    c.entities.channel_access_hash[100] = 555
    c.entities.user_access_hash[1] = 111

    async def invoke_api(req: Any, *, timeout: float = 0) -> Any:
        from telecraft.mtproto.rpc.sender import RpcErrorException
        raise RpcErrorException(code=400, message="USER_PRIVACY_RESTRICTED")

    c.invoke_api = invoke_api  # type: ignore[assignment]

    import pytest
    with pytest.raises(Exception):
        asyncio.run(c.add_users_to_group(
            ("channel", 100),
            [("user", 1)],
            on_error="raise",
        ))


# ===================== Get Group Members Tests =====================


def test_get_group_members_returns_list() -> None:
    """get_group_members should return a list of members."""
    c = _make_connected_client()
    c.entities.channel_access_hash[100] = 555

    async def invoke_api(req: Any, *, timeout: float = 0) -> Any:
        # Return mock participants
        user1 = type("_U", (), {"id": 1, "first_name": "User1", "bot": False})()
        user2 = type("_U", (), {"id": 2, "first_name": "User2", "bot": True})()
        return type("_R", (), {
            "participants": [
                type("_P", (), {"user_id": 1})(),
                type("_P", (), {"user_id": 2})(),
            ],
            "users": [user1, user2],
            "chats": [],
            "count": 2,
        })()

    c.invoke_api = invoke_api  # type: ignore[assignment]

    result = asyncio.run(c.get_group_members(("channel", 100), limit=10))
    assert isinstance(result, list)


# ===================== Transfer Members Tests =====================


def test_transfer_members_structure() -> None:
    """transfer_members should return proper structure."""
    c = _make_connected_client()
    c.entities.channel_access_hash[100] = 555
    c.entities.channel_access_hash[200] = 666
    c.self_user_id = 999

    call_count = [0]

    async def invoke_api(req: Any, *, timeout: float = 0) -> Any:
        call_count[0] += 1
        tl_name = getattr(req, "TL_NAME", "")

        if "getParticipants" in tl_name:
            # Return mock participants
            user1 = type("_U", (), {"id": 1, "first_name": "User1", "bot": False})()
            user2 = type("_U", (), {"id": 2, "first_name": "Bot", "bot": True})()
            return type("_R", (), {
                "participants": [
                    type("_P", (), {"user_id": 1})(),
                    type("_P", (), {"user_id": 2})(),
                ],
                "users": [user1, user2],
                "chats": [],
                "count": 2,
            })()
        else:
            # invite
            return type("_R", (), {"users": [], "chats": []})()

    c.invoke_api = invoke_api  # type: ignore[assignment]

    result = asyncio.run(c.transfer_members(
        ("channel", 100),
        ("channel", 200),
        exclude_bots=True,
    ))

    assert "success" in result
    assert "failed" in result
    assert "skipped" in result
    assert "source_total" in result


# ===================== Remove User Tests =====================


def test_remove_user_from_group_for_basic_group() -> None:
    """remove_user_from_group should call messages.deleteChatUser for basic groups."""
    c = _make_connected_client()
    c.entities.user_access_hash[200] = 777

    seen: list[Any] = []

    async def invoke_api(req: Any, *, timeout: float = 0) -> Any:
        seen.append(req)
        return type("_R", (), {"users": [], "chats": []})()

    c.invoke_api = invoke_api  # type: ignore[assignment]

    res = asyncio.run(c.remove_user_from_group(("chat", 100), ("user", 200)))
    assert res is not None
    assert len(seen) == 1
    assert getattr(seen[0], "TL_NAME", None) == "messages.deleteChatUser"


def test_remove_user_from_group_for_channel() -> None:
    """remove_user_from_group should use kick_user for channels."""
    c = _make_connected_client()
    c.entities.channel_access_hash[100] = 555
    c.entities.user_access_hash[200] = 777

    seen: list[Any] = []

    async def invoke_api(req: Any, *, timeout: float = 0) -> Any:
        seen.append(req)
        return type("_R", (), {"users": [], "chats": []})()

    c.invoke_api = invoke_api  # type: ignore[assignment]

    res = asyncio.run(c.remove_user_from_group(("channel", 100), ("user", 200)))
    assert res is not None
    # Should have called editBanned twice (ban then unban)
    assert len(seen) == 2
    assert all(getattr(r, "TL_NAME", None) == "channels.editBanned" for r in seen)
