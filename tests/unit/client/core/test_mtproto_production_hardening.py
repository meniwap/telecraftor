from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from telecraft.client import client as client_module
from telecraft.client import mtproto as mtproto_module
from telecraft.client.client import Client
from telecraft.client.mtproto import ClientInit, MtprotoClient
from telecraft.mtproto.rpc.sender import (
    DcMigrateError,
    FloodWaitConfig,
    ReceivedMessage,
    RpcSenderError,
)
from telecraft.mtproto.updates.engine import UpdatesEngine
from telecraft.mtproto.updates.state import UpdatesState
from telecraft.mtproto.updates.storage import save_updates_state_file
from telecraft.tl.generated.functions import AuthExportAuthorization, AuthImportAuthorization
from telecraft.tl.generated.types import MessageMediaPoll, Poll, TextWithEntities, UpdateConfig
from telecraft.tl.generated.types import UpdatesState as TlUpdatesState


def _dc_option(dc_id: int, host: str, port: int, **flags: object) -> SimpleNamespace:
    defaults: dict[str, object] = {
        "ipv6": False,
        "media_only": False,
        "cdn": False,
        "tcpo_only": False,
        "secret": None,
    }
    defaults.update(flags)
    return SimpleNamespace(id=dc_id, ip_address=host, port=port, **defaults)


def test_help_config_endpoints_replace_fallbacks_but_not_explicit_host() -> None:
    config = SimpleNamespace(
        dc_options=[
            _dc_option(2, "2001:db8::2", 443, ipv6=True),
            _dc_option(2, "203.0.113.2", 80),
            _dc_option(4, "203.0.113.40", 443, media_only=True),
            _dc_option(4, "203.0.113.4", 443),
        ]
    )

    client = MtprotoClient(network="prod", dc_id=2)
    client._ingest_dc_config(config)
    assert client._endpoint() == ("203.0.113.2", 80)
    assert client._endpoint_for_dc(4) == ("203.0.113.4", 443)

    explicit = MtprotoClient(network="prod", dc_id=2, host="127.0.0.1", port=9000)
    explicit._ingest_dc_config(config)
    assert explicit._endpoint() == ("127.0.0.1", 9000)
    assert explicit._endpoint_for_dc(4) == ("203.0.113.4", 443)


def test_update_config_refreshes_dynamic_endpoints_without_hiding_the_update() -> None:
    async def run() -> None:
        async def unexpected_engine_invoke(_req: Any) -> Any:
            raise AssertionError("ordinary updateConfig must not trigger getDifference")

        client = MtprotoClient(init=ClientInit(api_id=123, api_hash="hash"))
        engine = UpdatesEngine(invoke_api=unexpected_engine_invoke)
        engine.state = UpdatesState(pts=10, qts=2, date=100, seq=3)
        client._incoming = asyncio.Queue()
        client._updates_out = asyncio.Queue()
        client._updates_terminal = asyncio.get_running_loop().create_future()
        client._updates_engine = engine
        refreshed = SimpleNamespace(dc_options=[_dc_option(4, "203.0.113.44", 8443)])

        async def invoke_api(req: Any, *, timeout: float) -> Any:
            assert req.TL_NAME == "help.getConfig"
            assert timeout > 0
            client.config = refreshed
            client._ingest_dc_config(refreshed)
            return refreshed

        client.invoke_api = invoke_api  # type: ignore[method-assign]
        trigger = UpdateConfig()
        client._incoming.put_nowait(ReceivedMessage(msg_id=1, seqno=1, obj=trigger))
        task = asyncio.create_task(client._updates_loop(config_refresh_timeout=1.0))
        client._updates_task = task

        assert await asyncio.wait_for(client.recv_update(), timeout=1.0) is trigger
        assert client._endpoint_for_dc(4) == ("203.0.113.44", 8443)
        await client.stop_updates()

    asyncio.run(run())


def test_high_level_client_forwards_production_runtime_controls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    raw = SimpleNamespace(is_connected=False)

    def make_raw(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return raw

    monkeypatch.setattr(client_module, "MtprotoClient", make_raw)
    flood_wait = FloodWaitConfig(enabled=False)
    client = Client(
        strict_update_persistence=False,
        flood_wait_config=flood_wait,
        lock_session=False,
    )

    assert client.raw is raw
    assert captured["strict_update_persistence"] is False
    assert captured["flood_wait_config"] is flood_wait
    assert captured["lock_session"] is False


def test_search_messages_serializes_sender_filter_and_message_filter() -> None:
    async def run() -> None:
        client = MtprotoClient()
        client.entities.channel_access_hash[100] = 555
        client.entities.user_access_hash[200] = 777
        message_filter = SimpleNamespace(TL_NAME="inputMessagesFilterPhotos")
        seen: list[Any] = []

        async def invoke_api(req: Any, *, timeout: float) -> Any:
            _ = timeout
            seen.append(req)
            return SimpleNamespace()

        client.invoke_api = invoke_api  # type: ignore[method-assign]
        await client.search_messages(
            ("channel", 100),
            from_user=("user", 200),
            filter=message_filter,
        )

        assert len(seen) == 1
        assert seen[0].flags & 1
        assert seen[0].from_id.user_id == 200
        assert seen[0].filter is message_filter

    asyncio.run(run())


def test_transfer_members_excludes_admins_when_requested() -> None:
    async def run() -> None:
        client = MtprotoClient()
        users = [
            SimpleNamespace(id=10, bot=False),
            SimpleNamespace(id=20, bot=False),
        ]
        added: list[Any] = []

        async def get_members(*_args: Any, **_kwargs: Any) -> list[Any]:
            return users

        async def participants(*_args: Any, **_kwargs: Any) -> Any:
            yield SimpleNamespace(user_id=10)

        async def add_users(_group: Any, user_refs: list[Any], **_kwargs: Any) -> dict[str, Any]:
            added.extend(user_refs)
            return {"success": [20], "failed": [], "total": 1}

        client.get_group_members = get_members  # type: ignore[method-assign]
        client.iter_participants = participants  # type: ignore[method-assign]
        client.add_users_to_group = add_users  # type: ignore[method-assign]

        result = await client.transfer_members(
            ("channel", 1),
            ("channel", 2),
            exclude_bots=False,
            exclude_admins=True,
        )

        assert added == [("user", 20)]
        assert result["skipped"] == [(10, "admin")]

    asyncio.run(run())


def test_close_poll_fetches_and_resends_the_existing_poll_as_closed() -> None:
    async def run() -> None:
        client = MtprotoClient()
        client.entities.user_access_hash[100] = 555
        poll = Poll(
            id=7,
            flags=0,
            closed=None,
            public_voters=None,
            multiple_choice=None,
            quiz=None,
            open_answers=None,
            revoting_disabled=None,
            shuffle_answers=None,
            hide_results_until_close=None,
            creator=None,
            subscribers_only=None,
            question=TextWithEntities(text="Question", entities=[]),
            answers=[],
            close_period=None,
            close_date=None,
            countries_iso2=None,
            hash=123,
        )
        current = SimpleNamespace(
            messages=[
                SimpleNamespace(
                    id=42,
                    media=MessageMediaPoll(
                        flags=0,
                        poll=poll,
                        results=SimpleNamespace(),
                        attached_media=None,
                    ),
                )
            ]
        )
        seen: list[Any] = []

        async def invoke_api(req: Any, *, timeout: float) -> Any:
            _ = timeout
            seen.append(req)
            return current if len(seen) == 1 else "edited"

        client.invoke_api = invoke_api  # type: ignore[method-assign]
        assert await client.close_poll(("user", 100), 42) == "edited"

        assert seen[0].TL_NAME == "messages.getMessages"
        assert seen[1].TL_NAME == "messages.editMessage"
        assert seen[1].media.poll.closed is True
        assert seen[1].media.poll.flags & 1
        assert seen[1].media.poll.hash == 123

    asyncio.run(run())


def test_invoke_api_retries_rejected_request_once_after_primary_migration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        client = MtprotoClient()
        request = SimpleNamespace(TL_NAME="messages.sendMessage")
        calls = 0
        migrations: list[tuple[int, str]] = []

        async def invoke(req: Any, *, timeout: float, **_kwargs: Any) -> Any:
            nonlocal calls
            assert req is request
            assert timeout > 0
            calls += 1
            if calls == 1:
                raise DcMigrateError(
                    code=303,
                    message="USER_MIGRATE_4",
                    kind="USER",
                    dc_id=4,
                )
            return "ok"

        async def migrate(dc_id: int, *, kind: str, timeout: float) -> None:
            assert timeout > 0
            migrations.append((dc_id, kind))

        monkeypatch.setattr(client, "invoke", invoke)
        monkeypatch.setattr(client, "_migrate_primary_dc", migrate)

        assert await client.invoke_api(request, timeout=1.0) == "ok"
        assert calls == 2
        assert migrations == [(4, "USER")]

    asyncio.run(run())


def test_start_updates_can_migrate_without_releasing_lifecycle_exclusivity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        client = MtprotoClient(init=ClientInit(api_id=123, api_hash="hash"))
        client._incoming = asyncio.Queue()
        client._did_init_connection = True
        invoke_calls = 0
        migration_entered = asyncio.Event()
        release_migration = asyncio.Event()

        async def invoke(req: Any, *, timeout: float, **_kwargs: Any) -> Any:
            nonlocal invoke_calls
            _ = req
            assert timeout > 0
            invoke_calls += 1
            if invoke_calls == 1:
                raise DcMigrateError(
                    code=303,
                    message="USER_MIGRATE_4",
                    kind="USER",
                    dc_id=4,
                )
            return TlUpdatesState(pts=10, qts=2, date=100, seq=3, unread_count=0)

        async def perform(dc_id: int, *, kind: str, timeout: float) -> None:
            assert dc_id == 4
            assert kind == "USER"
            # This is the acquisition that previously deadlocked against the
            # lifecycle lock already held by start_updates.
            async with client._lifecycle_serialized(timeout=timeout):
                migration_entered.set()
                await release_migration.wait()
                client._dc_id = dc_id

        monkeypatch.setattr(client, "invoke", invoke)
        monkeypatch.setattr(client, "_perform_primary_dc_migration", perform)

        start_task = asyncio.create_task(client.start_updates(timeout=1.0))
        await asyncio.wait_for(migration_entered.wait(), timeout=0.5)
        close_task = asyncio.create_task(client.close())
        await asyncio.sleep(0)
        assert close_task.done() is False

        release_migration.set()
        await asyncio.wait_for(start_task, timeout=0.5)
        await asyncio.wait_for(close_task, timeout=0.5)
        assert invoke_calls == 2
        assert client._dc_id == 4

    asyncio.run(run())


def test_log_out_can_migrate_while_lifecycle_is_serialized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        client = MtprotoClient(init=ClientInit(api_id=123, api_hash="hash"))
        client._did_init_connection = True
        calls = 0

        async def invoke(req: Any, *, timeout: float, **_kwargs: Any) -> Any:
            nonlocal calls
            _ = req
            assert timeout > 0
            calls += 1
            if calls == 1:
                raise DcMigrateError(
                    code=303,
                    message="USER_MIGRATE_4",
                    kind="USER",
                    dc_id=4,
                )
            return "logged-out"

        async def perform(dc_id: int, *, kind: str, timeout: float) -> None:
            assert kind == "USER"
            async with client._lifecycle_serialized(timeout=timeout):
                client._dc_id = dc_id

        monkeypatch.setattr(client, "invoke", invoke)
        monkeypatch.setattr(client, "_perform_primary_dc_migration", perform)

        result = await asyncio.wait_for(client.log_out(timeout=1.0), timeout=0.5)

        assert result == "logged-out"
        assert calls == 2
        assert client._dc_id == 4

    asyncio.run(run())


def test_invoke_condition_wait_obeys_total_deadline() -> None:
    async def run() -> None:
        client = MtprotoClient()
        client._migration_in_progress = True

        with pytest.raises(RpcSenderError, match="total deadline"):
            await asyncio.wait_for(client.invoke(object(), timeout=0.01), timeout=0.5)

        assert client._active_invocations == 0
        assert client._invoke_condition.locked() is False

    asyncio.run(run())


def test_invoke_passes_only_remaining_deadline_to_sender() -> None:
    async def run() -> None:
        client = MtprotoClient()
        observed_timeouts: list[float] = []

        class Sender:
            is_healthy = True

            async def invoke_tl(
                self,
                req: Any,
                *,
                timeout: float,
                flood_wait_config: Any,
            ) -> str:
                _ = req, flood_wait_config
                observed_timeouts.append(timeout)
                return "ok"

        client._sender = Sender()  # type: ignore[assignment]
        client._migration_in_progress = True
        invoke_task = asyncio.create_task(client.invoke(object(), timeout=0.2))
        await asyncio.sleep(0.03)
        async with client._invoke_condition:
            client._migration_in_progress = False
            client._invoke_condition.notify_all()

        assert await asyncio.wait_for(invoke_task, timeout=0.5) == "ok"
        assert len(observed_timeouts) == 1
        assert 0 < observed_timeouts[0] < 0.19

    asyncio.run(run())


def test_invoke_wall_clock_deadline_does_not_wait_for_sender_cancellation_cleanup() -> None:
    async def run() -> None:
        client = MtprotoClient()
        cleanup_started = asyncio.Event()
        release_cleanup = asyncio.Event()

        class Sender:
            is_healthy = True

            async def invoke_tl(
                self,
                req: Any,
                *,
                timeout: float,
                flood_wait_config: Any,
            ) -> Any:
                _ = req, flood_wait_config

                async def blocked_send() -> None:
                    try:
                        await asyncio.Future()
                    except asyncio.CancelledError:
                        cleanup_started.set()
                        await release_cleanup.wait()
                        raise

                try:
                    await asyncio.wait_for(blocked_send(), timeout=timeout)
                except asyncio.TimeoutError as exc:
                    raise RpcSenderError("sender deadline") from exc
                raise AssertionError("unreachable")

        client._sender = Sender()  # type: ignore[assignment]
        started_at = asyncio.get_running_loop().time()
        invoke_task = asyncio.create_task(client.invoke(object(), timeout=0.03))
        try:
            # wait_for would itself wait for cancellation acknowledgement on
            # Python 3.10, so observe completion without cancelling the caller.
            await asyncio.sleep(0.1)
            assert invoke_task.done() is True
            with pytest.raises(RpcSenderError, match="total deadline"):
                await invoke_task
            assert asyncio.get_running_loop().time() - started_at < 0.15
            await asyncio.wait_for(cleanup_started.wait(), timeout=0.1)
            assert client._active_invocations == 1
            assert any(
                task.get_name() == "telecraft:invoke" for task in client._deferred_cleanup_tasks
            )
        finally:
            release_cleanup.set()
            if not invoke_task.done():
                await asyncio.wait_for(invoke_task, timeout=0.5)
            await _finish_deferred_cleanup(client)

        assert client._active_invocations == 0
        assert client._deferred_cleanup_tasks == set()

    asyncio.run(run())


def test_invoke_api_routes_file_migrate_to_cross_dc_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        client = MtprotoClient()
        request = SimpleNamespace(TL_NAME="upload.getFile")

        async def invoke(req: Any, *, timeout: float, **_kwargs: Any) -> Any:
            _ = req, timeout
            raise DcMigrateError(
                code=303,
                message="FILE_MIGRATE_5",
                kind="FILE",
                dc_id=5,
            )

        class Target:
            async def invoke_api(self, req: Any, *, timeout: float) -> Any:
                assert req is request
                assert timeout > 0
                return "file"

        async def client_for_dc(dc_id: int, *, timeout: float) -> Target:
            assert dc_id == 5
            assert timeout > 0
            return Target()

        monkeypatch.setattr(client, "invoke", invoke)
        monkeypatch.setattr(client, "_client_for_dc", client_for_dc)
        assert await client.invoke_api(request, timeout=1.0) == "file"

    asyncio.run(run())


class _BlockingMigrationClose:
    """A close operation that remains pending even if cancellation is requested."""

    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.closed = False
        self.ignored_cancellations = 0

    async def close(self) -> None:
        self.started.set()
        while not self.release.is_set():
            try:
                await self.release.wait()
            except asyncio.CancelledError:
                self.ignored_cancellations += 1
        self.closed = True


class _MigrationOldSender:
    is_healthy = True

    def __init__(self) -> None:
        self.closed = False
        self.forwarded: list[Any] = []

    async def invoke_tl(self, req: Any, **_kwargs: Any) -> Any:
        assert isinstance(req, AuthExportAuthorization)
        return SimpleNamespace(id=77, bytes=b"authorization")

    def _forward_incoming(self, item: Any) -> None:
        self.forwarded.append(item)

    async def close(self) -> None:
        self.closed = True


class _MigrationOldTransport:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class _MigrationCandidate:
    def __init__(
        self,
        *,
        connect_error: BaseException | None = None,
        blocking_close: _BlockingMigrationClose | None = None,
    ) -> None:
        self._transport: Any = SimpleNamespace(name="new-transport")
        self._sender: Any = SimpleNamespace(is_healthy=True, name="new-sender")
        self._state: Any = SimpleNamespace(auth_key_id=2)
        self._msg_id_gen: Any = SimpleNamespace()
        self._incoming: Any = asyncio.Queue()
        self._framing_name = "intermediate"
        self._did_init_connection = True
        self._dc_endpoints = {4: ("203.0.113.4", 443)}
        self.config = SimpleNamespace(dc_options=[])
        self.connect_error = connect_error
        self.blocking_close = blocking_close
        self.connected = False
        self.closed = False
        self.close_calls = 0

    async def connect(self, *, timeout: float) -> None:
        assert timeout > 0
        self.connected = True
        if self.connect_error is not None:
            raise self.connect_error

    async def invoke_api(self, req: Any, *, timeout: float) -> Any:
        assert timeout > 0
        assert isinstance(req, AuthImportAuthorization)
        return SimpleNamespace()

    async def close(self) -> None:
        self.close_calls += 1
        if self.blocking_close is not None:
            await self.blocking_close.close()
        self.closed = True


def _prepare_primary_migration(
    monkeypatch: pytest.MonkeyPatch,
    *,
    candidate: _MigrationCandidate,
    stale_child: _BlockingMigrationClose | None = None,
) -> tuple[MtprotoClient, _MigrationOldSender, _MigrationOldTransport]:
    client = MtprotoClient(
        network="prod",
        dc_id=2,
        init=ClientInit(api_id=123, api_hash="hash"),
    )
    client._dc_endpoints[4] = ("203.0.113.4", 443)
    old_sender = _MigrationOldSender()
    old_transport = _MigrationOldTransport()
    client._sender = old_sender  # type: ignore[assignment]
    client._transport = old_transport  # type: ignore[assignment]
    client._state = SimpleNamespace(auth_key_id=1)  # type: ignore[assignment]
    client._msg_id_gen = SimpleNamespace()  # type: ignore[assignment]
    client._incoming = asyncio.Queue()
    if stale_child is not None:
        client._media_clients[5] = stale_child  # type: ignore[assignment]
    monkeypatch.setattr(mtproto_module, "MtprotoClient", lambda **_kwargs: candidate)
    return client, old_sender, old_transport


async def _finish_deferred_cleanup(client: MtprotoClient) -> None:
    tasks = list(client._deferred_cleanup_tasks)
    if tasks:
        await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True),
            timeout=0.5,
        )
    await asyncio.sleep(0)


def test_primary_migration_transfers_authorization_and_adopts_new_connection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    async def run() -> None:
        client = MtprotoClient(
            network="prod",
            dc_id=2,
            session_path=tmp_path / "migrated.session.json",
            init=ClientInit(api_id=123, api_hash="hash"),
        )
        client._dc_endpoints[4] = ("203.0.113.4", 443)

        class OldSender:
            is_healthy = True

            def __init__(self) -> None:
                self.closed = False
                self.forwarded: list[Any] = []

            async def invoke_tl(self, req: Any, **_kwargs: Any) -> Any:
                assert isinstance(req, AuthExportAuthorization)
                assert req.dc_id == 4
                return SimpleNamespace(id=77, bytes=b"authorization")

            def _forward_incoming(self, item: Any) -> None:
                self.forwarded.append(item)

            async def close(self) -> None:
                self.closed = True

        class OldTransport:
            def __init__(self) -> None:
                self.closed = False

            async def close(self) -> None:
                self.closed = True

        old_sender = OldSender()
        old_transport = OldTransport()
        client._sender = old_sender  # type: ignore[assignment]
        client._transport = old_transport  # type: ignore[assignment]
        client._state = SimpleNamespace(auth_key_id=1)  # type: ignore[assignment]
        client._msg_id_gen = SimpleNamespace()  # type: ignore[assignment]
        client._incoming = asyncio.Queue()
        save_updates_state_file(
            tmp_path / "migrated.updates.json",
            UpdatesState(pts=10, qts=2, date=100, seq=3),
            auth_key_id="0100000000000000",
        )

        new_sender = SimpleNamespace(is_healthy=True)
        new_transport = SimpleNamespace()
        new_state = SimpleNamespace(auth_key_id=2)

        class Candidate:
            def __init__(self) -> None:
                self._transport: Any = new_transport
                self._sender: Any = new_sender
                self._state: Any = new_state
                self._msg_id_gen: Any = SimpleNamespace()
                self._incoming: Any = asyncio.Queue()
                self._framing_name = "intermediate"
                self._did_init_connection = True
                self._dc_endpoints = {4: ("203.0.113.4", 443)}
                self.config = SimpleNamespace(dc_options=[])
                self.imported: Any = None
                self.connected = False
                self.closed = False

            async def connect(self, *, timeout: float) -> None:
                assert timeout > 0
                self.connected = True

            async def invoke_api(self, req: Any, *, timeout: float) -> Any:
                assert timeout > 0
                assert isinstance(req, AuthImportAuthorization)
                self.imported = req
                return SimpleNamespace()

            async def close(self) -> None:
                self.closed = True

        candidate = Candidate()
        monkeypatch.setattr(mtproto_module, "MtprotoClient", lambda **_kwargs: candidate)
        persisted = False

        async def persist() -> None:
            nonlocal persisted
            persisted = True

        monkeypatch.setattr(client, "_persist_session", persist)

        await client._perform_primary_dc_migration(4, kind="USER", timeout=1.0)

        assert candidate.connected is True
        assert candidate.imported.id == 77
        assert candidate.imported.bytes == b"authorization"
        assert client._dc_id == 4
        assert client._sender is new_sender
        assert client._transport is new_transport
        assert old_sender.closed is True
        assert old_transport.closed is True
        assert persisted is True
        assert client._updates_state_auth_key_id_alias == "0100000000000000"

    asyncio.run(run())


def test_primary_migration_cleanup_has_hard_deadline_and_releases_serializers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        stale_child = _BlockingMigrationClose()
        candidate = _MigrationCandidate()
        client, old_sender, old_transport = _prepare_primary_migration(
            monkeypatch,
            candidate=candidate,
            stale_child=stale_child,
        )
        migration_task = asyncio.create_task(
            client._migrate_primary_dc(4, kind="USER", timeout=0.03)
        )
        started_at = asyncio.get_running_loop().time()
        try:
            # Do not use wait_for here: on Python 3.10 it waits for a coroutine
            # that suppresses cancellation.  The migration itself must finish.
            await asyncio.sleep(0.1)
            assert migration_task.done() is True
            with pytest.raises(mtproto_module.MtprotoClientError, match="Timed out migrating"):
                await migration_task
            assert asyncio.get_running_loop().time() - started_at < 0.15

            assert stale_child.started.is_set()
            assert stale_child.closed is False
            assert old_sender.closed is True
            assert old_transport.closed is True
            assert client._dc_id == 4
            assert stale_child in client._deferred_cleanup_resources
            assert any(
                "migration-stale-child" in task.get_name()
                for task in client._deferred_cleanup_tasks
            )
            assert client._migration_in_progress is False
            assert client._migration_lock.locked() is False
            assert client._lifecycle_lock.locked() is False
            assert client._lifecycle_owner is None
            assert client._lifecycle_depth == 0
        finally:
            stale_child.release.set()
            if not migration_task.done():
                await asyncio.wait_for(migration_task, timeout=0.5)
            await _finish_deferred_cleanup(client)

        assert stale_child.closed is True
        assert stale_child not in client._deferred_cleanup_resources

    asyncio.run(run())


def test_failed_migration_candidate_remains_owned_until_close_finishes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        blocking_close = _BlockingMigrationClose()
        candidate = _MigrationCandidate(
            connect_error=RuntimeError("candidate connect failed"),
            blocking_close=blocking_close,
        )
        client, _old_sender, _old_transport = _prepare_primary_migration(
            monkeypatch,
            candidate=candidate,
        )
        migration_task = asyncio.create_task(
            client._migrate_primary_dc(4, kind="USER", timeout=0.03)
        )
        try:
            await asyncio.sleep(0.1)
            assert migration_task.done() is True
            with pytest.raises(RuntimeError, match="candidate connect failed"):
                await migration_task

            assert blocking_close.started.is_set()
            assert candidate.closed is False
            assert candidate in client._deferred_cleanup_resources
            assert any(
                "migration-unsuccessful-candidate" in task.get_name()
                for task in client._deferred_cleanup_tasks
            )
            assert client._dc_id == 2
            assert client._migration_in_progress is False
            assert client._migration_lock.locked() is False
            assert client._lifecycle_lock.locked() is False
            assert client._lifecycle_owner is None
        finally:
            blocking_close.release.set()
            if not migration_task.done():
                await asyncio.wait_for(migration_task, timeout=0.5)
            await _finish_deferred_cleanup(client)

        assert candidate.closed is True
        assert candidate not in client._deferred_cleanup_resources

    asyncio.run(run())


def test_teardown_does_not_double_close_an_active_candidate_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        blocking_close = _BlockingMigrationClose()
        candidate = _MigrationCandidate(
            connect_error=RuntimeError("candidate connect failed"),
            blocking_close=blocking_close,
        )
        client, _old_sender, _old_transport = _prepare_primary_migration(
            monkeypatch,
            candidate=candidate,
        )
        try:
            with pytest.raises(RuntimeError, match="candidate connect failed"):
                await client._migrate_primary_dc(4, kind="USER", timeout=0.03)
            await asyncio.wait_for(blocking_close.started.wait(), timeout=0.1)
            assert candidate.close_calls == 1

            # The deferred coordinator still owns candidate.close().  Teardown
            # may close current resources, but must not race a second close on
            # this candidate.
            await client.close()
            assert candidate.close_calls == 1
            assert candidate.closed is False
            assert candidate in client._deferred_cleanup_resources
        finally:
            blocking_close.release.set()
            await _finish_deferred_cleanup(client)

        assert candidate.closed is True
        assert candidate not in client._deferred_cleanup_resources

    asyncio.run(run())


def test_teardown_retries_a_completed_failed_candidate_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailCloseOnceCandidate(_MigrationCandidate):
        async def close(self) -> None:
            self.close_calls += 1
            if self.close_calls == 1:
                raise RuntimeError("candidate close failed")
            self.closed = True

    async def run() -> None:
        candidate = FailCloseOnceCandidate(connect_error=RuntimeError("candidate connect failed"))
        client, _old_sender, _old_transport = _prepare_primary_migration(
            monkeypatch,
            candidate=candidate,
        )

        with pytest.raises(RuntimeError, match="candidate connect failed"):
            await client._migrate_primary_dc(4, kind="USER", timeout=0.2)
        await asyncio.sleep(0)
        assert candidate.close_calls == 1
        assert candidate in client._deferred_cleanup_resources

        await client.close()

        assert candidate.close_calls == 2
        assert candidate.closed is True
        assert candidate not in client._deferred_cleanup_resources

    asyncio.run(run())


def test_cancellation_after_adoption_keeps_old_resources_owned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        stale_child = _BlockingMigrationClose()
        candidate = _MigrationCandidate()
        new_sender = candidate._sender
        new_transport = candidate._transport
        client, old_sender, old_transport = _prepare_primary_migration(
            monkeypatch,
            candidate=candidate,
            stale_child=stale_child,
        )
        migration_task = asyncio.create_task(
            client._migrate_primary_dc(4, kind="USER", timeout=1.0)
        )
        try:
            await asyncio.wait_for(stale_child.started.wait(), timeout=0.5)
            migration_task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await migration_task

            assert client._dc_id == 4
            assert client._sender is new_sender
            assert client._transport is new_transport
            assert old_sender.closed is True
            assert old_transport.closed is True
            assert stale_child.closed is False
            assert 5 not in client._media_clients
            assert stale_child in client._deferred_cleanup_resources
            assert any(
                "migration-stale-child" in task.get_name()
                for task in client._deferred_cleanup_tasks
            )
            assert client._migration_in_progress is False
            assert client._migration_lock.locked() is False
            assert client._lifecycle_lock.locked() is False
            assert client._lifecycle_owner is None
            assert client._lifecycle_depth == 0
        finally:
            stale_child.release.set()
            await _finish_deferred_cleanup(client)

        assert stale_child.closed is True
        assert stale_child not in client._deferred_cleanup_resources

    asyncio.run(run())


def test_competing_migrations_follow_lifecycle_then_migration_lock_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        client = MtprotoClient(init=ClientInit(api_id=123, api_hash="hash"))
        lifecycle_held = asyncio.Event()
        run_inner_migration = asyncio.Event()
        performed: list[int] = []

        async def perform(dc_id: int, *, kind: str, timeout: float) -> None:
            assert kind == "USER"
            async with client._lifecycle_serialized(timeout=timeout):
                performed.append(dc_id)
                client._dc_id = dc_id
                await asyncio.sleep(0)

        monkeypatch.setattr(client, "_perform_primary_dc_migration", perform)

        async def lifecycle_holder() -> None:
            async with client._lifecycle_serialized():
                lifecycle_held.set()
                await run_inner_migration.wait()
                await client._migrate_primary_dc(4, kind="USER", timeout=0.5)

        holder_task = asyncio.create_task(lifecycle_holder())
        await asyncio.wait_for(lifecycle_held.wait(), timeout=0.5)
        competing_task = asyncio.create_task(
            client._migrate_primary_dc(5, kind="USER", timeout=0.5)
        )
        for _ in range(3):
            await asyncio.sleep(0)

        # A migration waiting for lifecycle serialization must not reserve the
        # inner migration lock and deadlock its current lifecycle owner.
        assert client._migration_lock.locked() is False
        run_inner_migration.set()
        await asyncio.wait_for(holder_task, timeout=0.5)
        await asyncio.wait_for(competing_task, timeout=0.5)

        assert performed == [4, 5]
        assert client._dc_id == 5
        assert client._migration_in_progress is False
        assert client._migration_lock.locked() is False
        assert client._lifecycle_lock.locked() is False
        assert client._lifecycle_owner is None
        assert client._lifecycle_depth == 0

    asyncio.run(run())
