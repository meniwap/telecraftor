from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

from telecraft.client.mtproto import ClientInit, MtprotoClient


def _make_connected_client() -> MtprotoClient:
    c = MtprotoClient(network="test", dc_id=2, init=ClientInit(api_id=1, api_hash="x"))
    c._transport = object()  # type: ignore[attr-defined]
    c._sender = object()  # type: ignore[attr-defined]
    c._state = object()  # type: ignore[attr-defined]
    return c


def test_get_me_parses_users_wrapper_response() -> None:
    c = _make_connected_client()
    me = SimpleNamespace(TL_NAME="user", id=123, access_hash=999, username="alice")

    async def invoke_api(_req: Any, *, timeout: float = 0) -> Any:
        _ = timeout
        return SimpleNamespace(users=[me])

    c.invoke_api = invoke_api  # type: ignore[assignment]

    out = asyncio.run(c.get_me())
    assert out is me
    assert c.self_user_id == 123
    assert c.entities.user_access_hash[123] == 999
    assert c.entities.username_to_peer["alice"] == ("user", 123)


def test_get_me_handles_list_response() -> None:
    c = _make_connected_client()
    me = SimpleNamespace(TL_NAME="user", id=321, access_hash=555)

    async def invoke_api(_req: Any, *, timeout: float = 0) -> Any:
        _ = timeout
        return [me]

    c.invoke_api = invoke_api  # type: ignore[assignment]

    out = asyncio.run(c.get_me())
    assert out is me
    assert c.self_user_id == 321


def test_get_me_returns_none_for_user_empty() -> None:
    c = _make_connected_client()
    me_empty = SimpleNamespace(TL_NAME="userEmpty", id=123)

    async def invoke_api(_req: Any, *, timeout: float = 0) -> Any:
        _ = timeout
        return SimpleNamespace(users=[me_empty])

    c.invoke_api = invoke_api  # type: ignore[assignment]

    out = asyncio.run(c.get_me())
    assert out is None
    assert c.self_user_id is None


def test_get_me_falls_back_to_get_full_user_when_vector_is_empty() -> None:
    c = _make_connected_client()
    me = SimpleNamespace(TL_NAME="user", id=777, access_hash=333)
    calls: list[str] = []

    async def invoke_api(req: Any, *, timeout: float = 0) -> Any:
        _ = timeout
        calls.append(getattr(req, "TL_NAME", ""))
        if getattr(req, "TL_NAME", "") == "users.getUsers":
            # Simulate top-level Vector<User> decode that has no "users" field.
            return SimpleNamespace(TL_NAME="vector")
        return SimpleNamespace(users=[me])

    c.invoke_api = invoke_api  # type: ignore[assignment]

    out = asyncio.run(c.get_me())
    assert out is me
    assert calls == ["users.getUsers", "users.getFullUser"]
