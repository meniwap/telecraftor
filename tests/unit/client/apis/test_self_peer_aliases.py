from __future__ import annotations

import asyncio
from typing import Any

import pytest

from telecraft.client.apis._utils import resolve_input_peer, resolve_input_user
from telecraft.client.entities import EntityCache
from telecraft.client.mtproto import ClientInit, MtprotoClient
from telecraft.client.peers import Peer
from telecraft.tl.generated.types import InputPeerSelf, InputUserSelf


def _client() -> MtprotoClient:
    return MtprotoClient(
        network="test",
        dc_id=2,
        init=ClientInit(api_id=1, api_hash="x"),
    )


@pytest.mark.parametrize("alias", ["self", "ME", " me "])
def test_resolve_peer_self_alias_returns_current_user(alias: str) -> None:
    client = _client()
    client.self_user_id = 123

    resolved = asyncio.run(client.resolve_peer(alias))

    assert resolved == Peer.user(123)
    assert client.entities.self_user_id == 123


def test_entity_cache_uses_self_constructors_without_access_hash() -> None:
    cache = EntityCache(self_user_id=123)

    assert isinstance(cache.input_peer(Peer.user(123)), InputPeerSelf)
    assert isinstance(cache.input_user(123), InputUserSelf)


def test_send_action_self_alias_uses_input_peer_self_without_access_hash() -> None:
    client = _client()
    client.self_user_id = 123
    seen: list[Any] = []

    async def invoke_api(request: Any, *, timeout: float) -> bool:
        seen.append((request, timeout))
        return True

    client.invoke_api = invoke_api  # type: ignore[assignment]

    assert asyncio.run(client.send_action("self", timeout=7.0)) is True
    assert isinstance(seen[0][0].peer, InputPeerSelf)
    assert seen[0][1] == 7.0


def test_resolve_peer_self_alias_fetches_current_user_when_not_cached() -> None:
    client = _client()
    calls: list[float] = []

    async def get_me(*, timeout: float = 0) -> Any:
        calls.append(timeout)
        client.self_user_id = 321
        return object()

    client.get_me = get_me  # type: ignore[assignment]

    resolved = asyncio.run(client.resolve_peer("self", timeout=7.0))

    assert resolved == Peer.user(321)
    assert calls == [7.0]


@pytest.mark.parametrize("username", ["@self", "@me"])
def test_resolve_peer_explicit_self_username_still_resolves_username(username: str) -> None:
    client = _client()
    seen: list[str] = []

    async def resolve_username(value: str, *, timeout: float = 0, force: bool = False) -> Peer:
        _ = timeout, force
        seen.append(value)
        return Peer.user(456)

    client.resolve_username = resolve_username  # type: ignore[assignment]

    resolved = asyncio.run(client.resolve_peer(username))

    assert resolved == Peer.user(456)
    assert seen == [username]


@pytest.mark.parametrize("alias", ["self", "ME", " me "])
def test_v2_resolvers_use_self_constructors_without_peer_lookup(alias: str) -> None:
    class Raw:
        async def resolve_peer(self, _peer: Any, *, timeout: float) -> Any:
            raise AssertionError("a self alias must not be resolved as a username")

    raw = Raw()

    assert isinstance(asyncio.run(resolve_input_peer(raw, alias, timeout=7.0)), InputPeerSelf)
    assert isinstance(asyncio.run(resolve_input_user(raw, alias, timeout=7.0)), InputUserSelf)


@pytest.mark.parametrize("alias", ["self", "ME", " me "])
def test_send_message_self_alias_uses_input_peer_self(alias: str) -> None:
    client = _client()
    seen: list[Any] = []

    async def fail_resolve(_ref: Any, *, timeout: float = 0) -> Peer:
        raise AssertionError("a self alias must not be resolved as a username")

    async def send_message_peer(peer: Any, text: str, **kwargs: Any) -> Any:
        seen.append((peer, text, kwargs))
        return True

    client.resolve_peer = fail_resolve  # type: ignore[assignment]
    client.send_message_peer = send_message_peer  # type: ignore[assignment]

    result = asyncio.run(client.send_message(alias, "hello", timeout=7.0))

    assert result is True
    assert isinstance(seen[0][0], InputPeerSelf)
    assert seen[0][1] == "hello"
    assert seen[0][2]["timeout"] == 7.0


@pytest.mark.parametrize("method", ["get_history", "iter_messages"])
@pytest.mark.parametrize("alias", ["self", "ME", " me "])
def test_history_self_alias_uses_input_peer_self(method: str, alias: str) -> None:
    client = _client()
    seen: list[Any] = []

    async def fail_resolve(_ref: Any, *, timeout: float = 0) -> Peer:
        raise AssertionError("a self alias must not be resolved as a username")

    async def invoke_api(request: Any, *, timeout: float = 0) -> Any:
        seen.append((request, timeout))
        return None

    client.resolve_peer = fail_resolve  # type: ignore[assignment]
    client.invoke_api = invoke_api  # type: ignore[assignment]

    if method == "get_history":
        assert asyncio.run(client.get_history(alias, limit=5, timeout=7.0)) == []
    else:

        async def consume() -> list[Any]:
            return [item async for item in client.iter_messages(alias, limit=5, timeout=7.0)]

        assert asyncio.run(consume()) == []

    assert len(seen) == 1
    request, timeout = seen[0]
    assert isinstance(request.peer, InputPeerSelf)
    assert timeout == 7.0
