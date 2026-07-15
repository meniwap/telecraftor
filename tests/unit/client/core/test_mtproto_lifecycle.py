from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from telecraft.client import mtproto as mtproto_module
from telecraft.client.mtproto import ClientInit, MtprotoClient, MtprotoClientError
from telecraft.mtproto.rpc.sender import RpcSenderError


class _FakeTransport:
    instances: list[_FakeTransport] = []

    def __init__(self, *, endpoint: object, framing: object) -> None:
        self.endpoint = endpoint
        self.framing = framing
        self.connected = False
        self.closed = False
        self.instances.append(self)

    async def connect(self) -> None:
        self.connected = True

    async def close(self) -> None:
        self.closed = True
        self.connected = False

    async def send(self, payload: bytes) -> None:
        _ = payload

    async def recv(self) -> bytes:
        await asyncio.Future()
        raise AssertionError("unreachable")


def _install_fake_network(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeTransport.instances.clear()
    monkeypatch.setattr(mtproto_module, "TcpTransport", _FakeTransport)

    async def exchange_auth_key(transport: object, *, rsa_keys: list[object]) -> Any:
        _ = transport, rsa_keys
        return SimpleNamespace(auth_key=b"\x11" * 256, server_salt=b"\x22" * 8)

    monkeypatch.setattr(mtproto_module, "exchange_auth_key", exchange_auth_key)


def test_connect_bootstrap_failure_tears_down_and_allows_reconnect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _run() -> None:
        _install_fake_network(monkeypatch)
        client = MtprotoClient(init=ClientInit(api_id=123, api_hash="hash"))

        async def fail_bootstrap(req: object, *, timeout: float = 20.0) -> object:
            _ = req, timeout
            raise RuntimeError("bootstrap failed")

        monkeypatch.setattr(client, "invoke_with_layer", fail_bootstrap)
        with pytest.raises(RuntimeError, match="bootstrap failed"):
            await client.connect()

        first_transport = _FakeTransport.instances[0]
        assert first_transport.closed is True
        assert client.is_connected is False
        assert client._transport is None
        assert client._sender is None
        assert client._state is None
        assert client._incoming is None

        async def successful_bootstrap(req: object, *, timeout: float = 20.0) -> object:
            _ = req, timeout
            return {"ok": True}

        monkeypatch.setattr(client, "invoke_with_layer", successful_bootstrap)
        await client.connect()
        assert client.is_connected is True
        assert len(_FakeTransport.instances) == 2
        await client.close()

    asyncio.run(_run())


def test_fresh_auth_does_not_reuse_entity_cache_from_an_older_login(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    async def _run() -> None:
        _install_fake_network(monkeypatch)
        client = MtprotoClient(session_path=tmp_path / "fresh.session.json")
        client.entities.user_access_hash[1] = 111
        client.entities.channel_access_hash[2] = 222

        def fail_if_loaded() -> None:
            raise AssertionError("fresh auth must not load an old entity cache")

        monkeypatch.setattr(client, "_load_entities_cache", fail_if_loaded)
        await client.connect()

        assert client.entities.user_access_hash == {}
        assert client.entities.channel_access_hash == {}
        await client.close()

    asyncio.run(_run())


def test_transport_connect_failure_still_closes_and_clears_partial_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingConnectTransport(_FakeTransport):
        async def connect(self) -> None:
            raise ConnectionError("connect failed")

    async def _run() -> None:
        _FakeTransport.instances.clear()
        monkeypatch.setattr(mtproto_module, "TcpTransport", FailingConnectTransport)
        client = MtprotoClient()

        with pytest.raises(ConnectionError, match="connect failed"):
            await client.connect()

        assert len(_FakeTransport.instances) == 1
        assert _FakeTransport.instances[0].closed is True
        assert client.is_connected is False
        assert client._transport is None
        assert client._sender is None
        assert client._state is None

    asyncio.run(_run())


def test_close_cleans_resources_even_when_session_persistence_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _run() -> None:
        _install_fake_network(monkeypatch)
        client = MtprotoClient()
        await client.connect()
        transport = _FakeTransport.instances[0]
        sender = client._sender
        assert sender is not None

        async def fail_persist() -> None:
            raise OSError("disk full")

        monkeypatch.setattr(client, "_persist_session", fail_persist)
        with pytest.raises(OSError, match="disk full"):
            await client.close()

        assert transport.closed is True
        assert sender.is_healthy is False
        assert client.is_connected is False
        assert client._transport is None
        assert client._sender is None
        assert client._state is None
        assert client._incoming is None

    asyncio.run(_run())


def test_close_cancels_updates_task_and_closes_transport_when_stop_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _run() -> None:
        _install_fake_network(monkeypatch)
        client = MtprotoClient()
        await client.connect()
        transport = _FakeTransport.instances[0]
        update_task = asyncio.create_task(asyncio.Event().wait())
        client._updates_task = update_task

        async def fail_stop_updates() -> None:
            raise RuntimeError("stop failed")

        monkeypatch.setattr(client, "stop_updates", fail_stop_updates)
        with pytest.raises(RuntimeError, match="stop failed"):
            await client.close()

        assert update_task.cancelled() is True
        assert transport.closed is True
        assert client.is_connected is False
        assert client._updates_task is None

    asyncio.run(_run())


def test_close_still_closes_transport_when_sender_close_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _run() -> None:
        _install_fake_network(monkeypatch)
        client = MtprotoClient()
        await client.connect()
        transport = _FakeTransport.instances[0]
        sender = client._sender
        assert sender is not None

        async def fail_sender_close() -> None:
            raise RuntimeError("sender close failed")

        monkeypatch.setattr(sender, "close", fail_sender_close)
        with pytest.raises(RuntimeError, match="sender close failed"):
            await client.close()

        assert transport.closed is True
        assert client.is_connected is False
        assert client._transport is None
        assert client._sender is None

    asyncio.run(_run())


def test_unhealthy_sender_is_not_connected_and_connect_replaces_stale_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _run() -> None:
        _install_fake_network(monkeypatch)
        client = MtprotoClient()
        await client.connect()
        stale_transport = _FakeTransport.instances[0]
        stale_sender = client._sender
        assert stale_sender is not None

        stale_sender._terminal_error = RpcSenderError("receiver stopped")
        assert client.is_connected is False

        await client.connect()
        assert stale_transport.closed is True
        assert client.is_connected is True
        assert client._sender is not stale_sender
        assert len(_FakeTransport.instances) == 2
        await client.close()

    asyncio.run(_run())


def test_concurrent_connect_and_close_calls_are_serialized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _run() -> None:
        _install_fake_network(monkeypatch)
        client = MtprotoClient()

        await asyncio.gather(client.connect(), client.connect())
        assert client.is_connected is True
        assert len(_FakeTransport.instances) == 1

        await asyncio.gather(client.close(), client.close())
        assert client.is_connected is False
        assert _FakeTransport.instances[0].closed is True

    asyncio.run(_run())


def test_client_close_releases_transport_send_instead_of_deadlocking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BlockingSendTransport(_FakeTransport):
        def __init__(self, *, endpoint: object, framing: object) -> None:
            super().__init__(endpoint=endpoint, framing=framing)
            self.send_started = asyncio.Event()
            self.release_send = asyncio.Event()

        async def send(self, payload: bytes) -> None:
            _ = payload
            self.send_started.set()
            await self.release_send.wait()

        async def close(self) -> None:
            self.release_send.set()
            await super().close()

    async def _run() -> None:
        _FakeTransport.instances.clear()
        monkeypatch.setattr(mtproto_module, "TcpTransport", BlockingSendTransport)

        async def exchange_auth_key(transport: object, *, rsa_keys: list[object]) -> Any:
            _ = transport, rsa_keys
            return SimpleNamespace(auth_key=b"\x11" * 256, server_salt=b"\x22" * 8)

        monkeypatch.setattr(mtproto_module, "exchange_auth_key", exchange_auth_key)
        client = MtprotoClient()
        await client.connect()
        sender = client._sender
        transport = client._transport
        assert sender is not None
        assert isinstance(transport, BlockingSendTransport)

        from telecraft.mtproto.rpc.sender import _PendingCall

        call = _PendingCall(
            req_bytes=b"request!",
            future=asyncio.get_running_loop().create_future(),
        )
        send_task = asyncio.create_task(sender._send_new_attempt(call))
        await transport.send_started.wait()

        await asyncio.wait_for(client.close(), timeout=1.0)
        assert transport.closed is True
        with pytest.raises(RpcSenderError, match="closed"):
            await call.future
        with pytest.raises(RpcSenderError, match="closed"):
            await send_task

    asyncio.run(_run())


def test_concurrent_start_updates_publishes_only_one_consumer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BarrierEngine:
        instances = 0
        initialize_started = asyncio.Event()
        initialize_release = asyncio.Event()

        def __init__(self, **kwargs: object) -> None:
            _ = kwargs
            type(self).instances += 1

        async def initialize(self, *, initial_state: object = None) -> None:
            _ = initial_state
            type(self).initialize_started.set()
            await type(self).initialize_release.wait()

        def take_initial_catch_up(self) -> None:
            return None

    async def _run() -> None:
        BarrierEngine.instances = 0
        BarrierEngine.initialize_started = asyncio.Event()
        BarrierEngine.initialize_release = asyncio.Event()
        monkeypatch.setattr(mtproto_module, "UpdatesEngine", BarrierEngine)
        client = MtprotoClient(init=ClientInit(api_id=123, api_hash="hash"))
        client._incoming = asyncio.Queue()

        first = asyncio.create_task(client.start_updates())
        await BarrierEngine.initialize_started.wait()
        second = asyncio.create_task(client.start_updates())
        await asyncio.sleep(0)
        assert second.done() is False

        BarrierEngine.initialize_release.set()
        await asyncio.gather(first, second)

        assert BarrierEngine.instances == 1
        assert client._updates_task is not None
        assert client._updates_task.done() is False
        await client.stop_updates()

    asyncio.run(_run())


def test_stop_updates_unblocks_pending_recv_update() -> None:
    async def _run() -> None:
        client = MtprotoClient()
        client._updates_out = asyncio.Queue()
        client._updates_terminal = asyncio.get_running_loop().create_future()
        waiting = asyncio.create_task(client.recv_update())
        await asyncio.sleep(0)

        await client.stop_updates()

        with pytest.raises(MtprotoClientError, match="Updates stopped"):
            await asyncio.wait_for(waiting, timeout=1.0)

    asyncio.run(_run())
