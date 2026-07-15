from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from telecraft.client.mtproto import MtprotoClient, MtprotoClientError
from telecraft.mtproto.rpc.sender import ReceivedMessage, ReceiverTerminated, RpcSenderError
from telecraft.mtproto.updates.engine import AppliedUpdates, UpdatesEngine
from telecraft.mtproto.updates.state import UpdatesState
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
