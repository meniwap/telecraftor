"""Tests for group/channel creation and management methods."""
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


# ===================== Create Group/Channel Tests =====================


def test_create_group_calls_messages_create_chat() -> None:
    """create_group should call messages.createChat."""
    c = _make_connected_client()
    c.entities.user_access_hash[100] = 111
    c.entities.user_access_hash[200] = 222

    seen: list[Any] = []

    async def invoke_api(req: Any, *, timeout: float = 0) -> Any:
        seen.append(req)
        return type("_R", (), {"users": [], "chats": [], "updates": []})()

    c.invoke_api = invoke_api  # type: ignore[assignment]

    res = asyncio.run(c.create_group("Test Group", [("user", 100), ("user", 200)]))
    assert res is not None
    assert len(seen) == 1
    assert getattr(seen[0], "TL_NAME", None) == "messages.createChat"
    assert getattr(seen[0], "title", None) == "Test Group"


def test_create_channel_calls_channels_create_channel() -> None:
    """create_channel should call channels.createChannel."""
    c = _make_connected_client()

    seen: list[Any] = []

    async def invoke_api(req: Any, *, timeout: float = 0) -> Any:
        seen.append(req)
        return type("_R", (), {"users": [], "chats": [], "updates": []})()

    c.invoke_api = invoke_api  # type: ignore[assignment]

    res = asyncio.run(c.create_channel("Test Channel", "Description", broadcast=True))
    assert res is not None
    assert len(seen) == 1
    assert getattr(seen[0], "TL_NAME", None) == "channels.createChannel"
    assert getattr(seen[0], "title", None) == "Test Channel"
    assert getattr(seen[0], "broadcast", None) is True


def test_create_supergroup_sets_megagroup_flag() -> None:
    """create_channel with megagroup=True should set the megagroup flag."""
    c = _make_connected_client()

    seen: list[Any] = []

    async def invoke_api(req: Any, *, timeout: float = 0) -> Any:
        seen.append(req)
        return type("_R", (), {"users": [], "chats": [], "updates": []})()

    c.invoke_api = invoke_api  # type: ignore[assignment]

    res = asyncio.run(c.create_channel("Test Supergroup", "Desc", broadcast=False, megagroup=True))
    assert res is not None
    assert len(seen) == 1
    assert getattr(seen[0], "megagroup", None) is True


# ===================== Set Title Tests =====================


def test_set_chat_title_for_basic_group() -> None:
    """set_chat_title should call messages.editChatTitle for basic groups."""
    c = _make_connected_client()

    seen: list[Any] = []

    async def invoke_api(req: Any, *, timeout: float = 0) -> Any:
        seen.append(req)
        return type("_R", (), {"users": [], "chats": []})()

    c.invoke_api = invoke_api  # type: ignore[assignment]

    res = asyncio.run(c.set_chat_title(("chat", 12345), "New Title"))
    assert res is not None
    assert len(seen) == 1
    assert getattr(seen[0], "TL_NAME", None) == "messages.editChatTitle"
    assert getattr(seen[0], "title", None) == "New Title"


def test_set_chat_title_for_channel() -> None:
    """set_chat_title should call channels.editTitle for channels."""
    c = _make_connected_client()
    c.entities.channel_access_hash[12345] = 999

    seen: list[Any] = []

    async def invoke_api(req: Any, *, timeout: float = 0) -> Any:
        seen.append(req)
        return type("_R", (), {"users": [], "chats": []})()

    c.invoke_api = invoke_api  # type: ignore[assignment]

    res = asyncio.run(c.set_chat_title(("channel", 12345), "New Title"))
    assert res is not None
    assert len(seen) == 1
    assert getattr(seen[0], "TL_NAME", None) == "channels.editTitle"


# ===================== Common Chats Tests =====================


def test_get_common_chats_calls_messages_get_common_chats() -> None:
    """get_common_chats should call messages.getCommonChats."""
    c = _make_connected_client()
    c.entities.user_access_hash[123] = 456

    seen: list[Any] = []

    async def invoke_api(req: Any, *, timeout: float = 0) -> Any:
        seen.append(req)
        return type("_R", (), {"chats": []})()

    c.invoke_api = invoke_api  # type: ignore[assignment]

    res = asyncio.run(c.get_common_chats(("user", 123), limit=50))
    assert isinstance(res, list)
    assert len(seen) == 1
    assert getattr(seen[0], "TL_NAME", None) == "messages.getCommonChats"
    assert getattr(seen[0], "limit", None) == 50


# ===================== Mark Read Tests =====================


def test_mark_read_for_regular_chat() -> None:
    """mark_read should call messages.readHistory for regular chats."""
    c = _make_connected_client()
    c.entities.user_access_hash[123] = 456

    seen: list[Any] = []

    async def invoke_api(req: Any, *, timeout: float = 0) -> Any:
        seen.append(req)
        return type("_R", (), {"pts": 1, "pts_count": 1})()

    c.invoke_api = invoke_api  # type: ignore[assignment]

    res = asyncio.run(c.mark_read(("user", 123)))
    assert res is not None
    assert len(seen) == 1
    assert getattr(seen[0], "TL_NAME", None) == "messages.readHistory"


def test_mark_read_for_channel() -> None:
    """mark_read should call channels.readHistory for channels."""
    c = _make_connected_client()
    c.entities.channel_access_hash[123] = 456

    seen: list[Any] = []

    async def invoke_api(req: Any, *, timeout: float = 0) -> Any:
        seen.append(req)
        return True

    c.invoke_api = invoke_api  # type: ignore[assignment]

    res = asyncio.run(c.mark_read(("channel", 123)))
    assert res is True
    assert len(seen) == 1
    assert getattr(seen[0], "TL_NAME", None) == "channels.readHistory"


# ===================== Delete History Tests =====================


def test_delete_chat_history_calls_messages_delete_history() -> None:
    """delete_chat_history should call messages.deleteHistory."""
    c = _make_connected_client()
    c.entities.user_access_hash[123] = 456

    seen: list[Any] = []

    async def invoke_api(req: Any, *, timeout: float = 0) -> Any:
        seen.append(req)
        return type("_R", (), {"pts": 1, "pts_count": 1, "offset": 0})()

    c.invoke_api = invoke_api  # type: ignore[assignment]

    res = asyncio.run(c.delete_chat_history(("user", 123), just_clear=True, revoke=False))
    assert res is not None
    assert len(seen) == 1
    assert getattr(seen[0], "TL_NAME", None) == "messages.deleteHistory"


# ===================== Add User to Group Tests =====================


def test_add_user_to_group_for_basic_group() -> None:
    """add_user_to_group should call messages.addChatUser for basic groups."""
    c = _make_connected_client()
    c.entities.user_access_hash[200] = 777

    seen: list[Any] = []

    async def invoke_api(req: Any, *, timeout: float = 0) -> Any:
        seen.append(req)
        return type("_R", (), {"users": [], "chats": []})()

    c.invoke_api = invoke_api  # type: ignore[assignment]

    res = asyncio.run(c.add_user_to_group(("chat", 100), ("user", 200)))
    assert res is not None
    assert len(seen) == 1
    assert getattr(seen[0], "TL_NAME", None) == "messages.addChatUser"


def test_add_user_to_group_for_channel() -> None:
    """add_user_to_group should call channels.inviteToChannel for channels."""
    c = _make_connected_client()
    c.entities.channel_access_hash[100] = 555
    c.entities.user_access_hash[200] = 777

    seen: list[Any] = []

    async def invoke_api(req: Any, *, timeout: float = 0) -> Any:
        seen.append(req)
        return type("_R", (), {"users": [], "chats": []})()

    c.invoke_api = invoke_api  # type: ignore[assignment]

    res = asyncio.run(c.add_user_to_group(("channel", 100), ("user", 200)))
    assert res is not None
    assert len(seen) == 1
    assert getattr(seen[0], "TL_NAME", None) == "channels.inviteToChannel"
