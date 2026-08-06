from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from telecraft.client.mtproto import MtprotoClient, MtprotoClientError
from telecraft.mtproto.rpc.sender import ReceivedMessage, ReceiverTerminated, RpcSenderError
from telecraft.mtproto.updates.engine import AppliedUpdates, UpdatesEngine
from telecraft.mtproto.updates.state import UpdatesState
from telecraft.mtproto.updates.storage import load_updates_state_file, save_updates_state_file
from telecraft.tl.generated.types import Updates


def _prepared_client(
    *,
    output_size: int,
) -> tuple[
    MtprotoClient,
    UpdatesEngine,
    asyncio.Queue[ReceivedMessage | ReceiverTerminated],
]:
    async def unexpected_invoke(_req: Any) -> Any:
        raise AssertionError("contiguous test update must not use the network")

    client = MtprotoClient()
    engine = UpdatesEngine(invoke_api=unexpected_invoke)
    engine.state = UpdatesState(pts=0, qts=0, date=100, seq=0)
    incoming: asyncio.Queue[ReceivedMessage | ReceiverTerminated] = asyncio.Queue()
    client._incoming = incoming
    client._updates_out = asyncio.Queue(maxsize=output_size)
    client._updates_engine = engine
    client._updates_terminal = asyncio.get_running_loop().create_future()
    return client, engine, incoming


def test_full_output_queue_backpressures_and_cancel_rolls_back_state() -> None:
    async def run() -> None:
        client, engine, incoming = _prepared_client(output_size=1)
        assert client._updates_out is not None
        client._updates_out.put_nowait("already queued")
        update = SimpleNamespace(TL_NAME="updateIncoming", pts=1, pts_count=1)
        incoming.put_nowait(ReceivedMessage(msg_id=1, seqno=1, obj=update))

        task = asyncio.create_task(client._updates_loop())
        client._updates_task = task
        for _ in range(20):
            if engine.state is not None and engine.state.pts == 1:
                break
            await asyncio.sleep(0)

        assert engine.state == UpdatesState(pts=1, qts=0, date=100, seq=0)
        assert not task.done(), "producer should wait while the bounded queue is full"

        await client.stop_updates()

        assert engine.state == UpdatesState(pts=0, qts=0, date=100, seq=0)
        assert client._updates_terminal is not None
        assert isinstance(client._updates_terminal.result(), MtprotoClientError)

    asyncio.run(run())


def test_backpressure_delivers_entire_batch_in_order_without_loss() -> None:
    async def run() -> None:
        client, engine, incoming = _prepared_client(output_size=1)
        first = SimpleNamespace(TL_NAME="updateFirst", pts=1, pts_count=1)
        second = SimpleNamespace(TL_NAME="updateSecond", pts=2, pts_count=1)
        envelope = Updates(
            updates=[first, second],
            users=[],
            chats=[],
            date=200,
            seq=1,
        )
        incoming.put_nowait(ReceivedMessage(msg_id=1, seqno=1, obj=envelope))
        task = asyncio.create_task(client._updates_loop())
        client._updates_task = task

        received_first = await asyncio.wait_for(client.recv_update(), timeout=1.0)
        received_second = await asyncio.wait_for(client.recv_update(), timeout=1.0)
        await asyncio.sleep(0)

        assert [received_first, received_second] == [first, second]
        assert engine.state == UpdatesState(pts=2, qts=0, date=200, seq=1)

        await client.stop_updates()
        assert engine.state == UpdatesState(pts=2, qts=0, date=200, seq=1)

    asyncio.run(run())


def test_receiver_termination_wakes_pending_recv_update_with_error() -> None:
    async def run() -> None:
        client, _engine, incoming = _prepared_client(output_size=1)
        task = asyncio.create_task(client._updates_loop())
        client._updates_task = task
        waiter = asyncio.create_task(client.recv_update())
        await asyncio.sleep(0)

        terminal_error = RpcSenderError("receiver failed")
        incoming.put_nowait(ReceiverTerminated(error=terminal_error))

        with pytest.raises(RpcSenderError, match="receiver failed"):
            await asyncio.wait_for(waiter, timeout=1.0)
        await asyncio.wait_for(task, timeout=1.0)
        await client.stop_updates()

    asyncio.run(run())


def test_startup_catch_up_batch_is_emitted_before_live_updates() -> None:
    async def run() -> None:
        client, engine, _incoming = _prepared_client(output_size=1)
        checkpoint = UpdatesState(pts=0, qts=0, date=100, seq=0)
        engine.state = UpdatesState(pts=1, qts=0, date=150, seq=1)
        offline_update = SimpleNamespace(TL_NAME="updateWhileOffline")
        catch_up = (
            checkpoint,
            AppliedUpdates(
                updates=[offline_update],
                new_messages=[],
                users=[],
                chats=[],
            ),
        )

        task = asyncio.create_task(client._updates_loop(initial_catch_up=catch_up))
        client._updates_task = task

        assert await asyncio.wait_for(client.recv_update(), timeout=1.0) is offline_update
        await asyncio.sleep(0)
        await client.stop_updates()
        assert engine.state == UpdatesState(pts=1, qts=0, date=150, seq=1)

    asyncio.run(run())


def test_checkpoint_write_failure_is_observable_and_rolls_back_protocol_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    async def run() -> None:
        client, engine, incoming = _prepared_client(output_size=2)
        client._session_path = tmp_path / "strict.session.json"
        client._state = SimpleNamespace(auth_key_id=1)  # type: ignore[assignment]
        update = SimpleNamespace(TL_NAME="updateIncoming", pts=1, pts_count=1)
        incoming.put_nowait(ReceivedMessage(msg_id=1, seqno=1, obj=update))

        def fail_save(*_args: Any, **_kwargs: Any) -> None:
            raise OSError("disk full")

        monkeypatch.setattr(
            "telecraft.mtproto.updates.storage.save_updates_state_file",
            fail_save,
        )
        task = asyncio.create_task(client._updates_loop())
        client._updates_task = task
        await asyncio.wait_for(task, timeout=1.0)

        assert engine.state == UpdatesState(pts=0, qts=0, date=100, seq=0)
        assert isinstance(client.last_persistence_error, OSError)
        assert client._updates_out is not None
        assert client._updates_out.get_nowait() is update
        assert client._updates_terminal is not None
        assert isinstance(client._updates_terminal.result(), MtprotoClientError)
        client._updates_task = None

    asyncio.run(run())


def test_persist_updates_state_includes_runtime_channel_cursors(tmp_path) -> None:
    async def unused_invoke(_req: Any) -> Any:
        raise AssertionError("persistence must not invoke Telegram")

    client = MtprotoClient(session_path=tmp_path / "durable.session.json")
    client._state = SimpleNamespace(auth_key_id=1)  # type: ignore[assignment]
    engine = UpdatesEngine(invoke_api=unused_invoke)
    engine.state = UpdatesState(pts=10, qts=2, date=100, seq=3)
    engine._channel_pts[100] = 80
    client._updates_engine = engine

    client._persist_updates_state(force=True)

    persisted = load_updates_state_file(
        tmp_path / "durable.updates.json",
        expected_auth_key_id="0100000000000000",
    )
    assert persisted.channel_pts == {100: 80}


def test_previous_dc_checkpoint_alias_is_accepted_then_rebound(tmp_path) -> None:
    session_path = tmp_path / "migrated.session.json"
    checkpoint_path = tmp_path / "migrated.updates.json"
    old_auth_key_id = "0100000000000000"
    new_auth_key_id = "0200000000000000"
    old_checkpoint = UpdatesState(
        pts=10,
        qts=2,
        date=100,
        seq=3,
        channel_pts={100: 80},
    )
    save_updates_state_file(
        checkpoint_path,
        old_checkpoint,
        auth_key_id=old_auth_key_id,
    )

    async def unused_invoke(_req: Any) -> Any:
        raise AssertionError("checkpoint rebinding must not invoke Telegram")

    client = MtprotoClient(session_path=session_path)
    client._state = SimpleNamespace(auth_key_id=2)  # type: ignore[assignment]
    client._updates_state_auth_key_id_alias = old_auth_key_id

    loaded = client._load_updates_state()
    assert loaded is not None
    assert loaded.channel_pts == {100: 80}

    engine = UpdatesEngine(invoke_api=unused_invoke)
    engine.state = loaded
    engine._channel_pts = dict(loaded.channel_pts)
    client._updates_engine = engine
    client._persist_updates_state(force=True)

    assert client._updates_state_auth_key_id_alias is None
    rebound = load_updates_state_file(
        checkpoint_path,
        expected_auth_key_id=new_auth_key_id,
    )
    assert rebound.channel_pts == {100: 80}
