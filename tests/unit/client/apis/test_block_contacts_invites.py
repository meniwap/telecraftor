"""Tests for block/unblock, contacts, and invite links methods."""

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


# ===================== Block/Unblock Tests =====================


def test_block_user_calls_contacts_block() -> None:
    """block_user should call contacts.block."""
    c = _make_connected_client()
    c.entities.user_access_hash[123] = 456

    seen: list[Any] = []

    async def invoke_api(req: Any, *, timeout: float = 0) -> Any:
        seen.append(req)
        return True

    c.invoke_api = invoke_api  # type: ignore[assignment]

    res = asyncio.run(c.block_user(("user", 123)))
    assert res is True
    assert len(seen) == 1
    assert getattr(seen[0], "TL_NAME", None) == "contacts.block"


def test_unblock_user_calls_contacts_unblock() -> None:
    """unblock_user should call contacts.unblock."""
    c = _make_connected_client()
    c.entities.user_access_hash[123] = 456

    seen: list[Any] = []

    async def invoke_api(req: Any, *, timeout: float = 0) -> Any:
        seen.append(req)
        return True

    c.invoke_api = invoke_api  # type: ignore[assignment]

    res = asyncio.run(c.unblock_user(("user", 123)))
    assert res is True
    assert len(seen) == 1
    assert getattr(seen[0], "TL_NAME", None) == "contacts.unblock"


def test_get_blocked_users_calls_contacts_get_blocked() -> None:
    """get_blocked_users should call contacts.getBlocked."""
    c = _make_connected_client()

    seen: list[Any] = []

    async def invoke_api(req: Any, *, timeout: float = 0) -> Any:
        seen.append(req)
        return type("_B", (), {"users": [], "blocked": []})()

    c.invoke_api = invoke_api  # type: ignore[assignment]

    res = asyncio.run(c.get_blocked_users(limit=50))
    assert isinstance(res, list)
    assert len(seen) == 1
    assert getattr(seen[0], "TL_NAME", None) == "contacts.getBlocked"
    assert getattr(seen[0], "limit", None) == 50


# ===================== Contacts Tests =====================


def test_get_contacts_calls_contacts_get_contacts() -> None:
    """get_contacts should call contacts.getContacts."""
    c = _make_connected_client()

    seen: list[Any] = []

    async def invoke_api(req: Any, *, timeout: float = 0) -> Any:
        seen.append(req)
        return type("_C", (), {"users": []})()

    c.invoke_api = invoke_api  # type: ignore[assignment]

    res = asyncio.run(c.get_contacts())
    assert isinstance(res, list)
    assert len(seen) == 1
    assert getattr(seen[0], "TL_NAME", None) == "contacts.getContacts"


# ===================== Invite Links Tests =====================


def test_create_invite_link_calls_messages_export_chat_invite() -> None:
    """create_invite_link should call messages.exportChatInvite."""
    c = _make_connected_client()
    c.entities.channel_access_hash[100] = 555

    seen: list[Any] = []

    async def invoke_api(req: Any, *, timeout: float = 0) -> Any:
        seen.append(req)
        return type("_I", (), {"link": "https://t.me/+abc123"})()

    c.invoke_api = invoke_api  # type: ignore[assignment]

    res = asyncio.run(c.create_invite_link(("channel", 100), usage_limit=10, title="Test"))
    assert res is not None
    assert len(seen) == 1
    assert getattr(seen[0], "TL_NAME", None) == "messages.exportChatInvite"


def test_revoke_invite_link_calls_messages_edit_exported_chat_invite() -> None:
    """revoke_invite_link should call messages.editExportedChatInvite with revoked=True."""
    c = _make_connected_client()
    c.entities.channel_access_hash[100] = 555

    seen: list[Any] = []

    async def invoke_api(req: Any, *, timeout: float = 0) -> Any:
        seen.append(req)
        return type("_I", (), {"invite": type("_", (), {"revoked": True})()})()

    c.invoke_api = invoke_api  # type: ignore[assignment]

    res = asyncio.run(c.revoke_invite_link(("channel", 100), "https://t.me/+abc123"))
    assert res is not None
    assert len(seen) == 1
    assert getattr(seen[0], "TL_NAME", None) == "messages.editExportedChatInvite"
    assert getattr(seen[0], "revoked", None) is True


def test_delete_invite_link_calls_messages_delete_exported_chat_invite() -> None:
    """delete_invite_link should call messages.deleteExportedChatInvite."""
    c = _make_connected_client()
    c.entities.channel_access_hash[100] = 555

    seen: list[Any] = []

    async def invoke_api(req: Any, *, timeout: float = 0) -> Any:
        seen.append(req)
        return True

    c.invoke_api = invoke_api  # type: ignore[assignment]

    res = asyncio.run(c.delete_invite_link(("channel", 100), "https://t.me/+abc123"))
    assert res is True
    assert len(seen) == 1
    assert getattr(seen[0], "TL_NAME", None) == "messages.deleteExportedChatInvite"


def test_get_invite_links_calls_messages_get_exported_chat_invites() -> None:
    """get_invite_links should call messages.getExportedChatInvites."""
    c = _make_connected_client()
    c.entities.channel_access_hash[100] = 555
    c.entities.user_access_hash[999] = 888
    c.self_user_id = 999

    seen: list[Any] = []

    async def invoke_api(req: Any, *, timeout: float = 0) -> Any:
        seen.append(req)
        return type("_I", (), {"users": [], "invites": []})()

    c.invoke_api = invoke_api  # type: ignore[assignment]

    res = asyncio.run(c.get_invite_links(("channel", 100), limit=50))
    assert isinstance(res, list)
    assert len(seen) == 1
    assert getattr(seen[0], "TL_NAME", None) == "messages.getExportedChatInvites"
    assert getattr(seen[0], "limit", None) == 50
