from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from telecraft.mtproto.rpc.sender import (
    DcMigrateError,
    FloodWaitError,
    MtprotoEncryptedSender,
    ReceivedMessage,
    RpcSenderError,
    UpdatesRecoveryRequired,
    _PendingCall,
)
from telecraft.tl.codec import RpcResult
from telecraft.tl.generated.types import RpcError


def _sender(*, incoming: asyncio.Queue[Any] | None = None) -> MtprotoEncryptedSender:
    return MtprotoEncryptedSender(
        SimpleNamespace(),
        state=SimpleNamespace(),
        msg_id_gen=SimpleNamespace(),
        incoming_queue=incoming,
    )


def test_rpc_migrate_error_is_structured() -> None:
    async def run() -> None:
        sender = _sender()
        future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        call = _PendingCall(req_bytes=b"request", future=future)
        sender._pending[123] = call

        await sender._handle_message(
            ReceivedMessage(
                msg_id=999,
                seqno=1,
                obj=RpcResult(
                    req_msg_id=123,
                    result=RpcError(error_code=303, error_message="PHONE_MIGRATE_4"),
                ),
            )
        )

        with pytest.raises(DcMigrateError) as raised:
            await future
        assert raised.value.kind == "PHONE"
        assert raised.value.dc_id == 4
        assert raised.value.code == 303

    asyncio.run(run())


def test_full_updates_queue_schedules_recovery_without_blocking_receiver() -> None:
    async def run() -> None:
        incoming: asyncio.Queue[Any] = asyncio.Queue(maxsize=1)
        incoming.put_nowait(ReceivedMessage(msg_id=1, seqno=1, obj=object()))
        sender = _sender(incoming=incoming)

        await asyncio.wait_for(
            sender._handle_message(
                ReceivedMessage(
                    msg_id=2,
                    seqno=1,
                    obj=SimpleNamespace(TL_NAME="updateNewMessage"),
                )
            ),
            timeout=0.1,
        )

        assert incoming.qsize() == 1
        assert incoming.get_nowait() == UpdatesRecoveryRequired(reason="incoming_queue_overflow")

    asyncio.run(run())


def test_total_deadline_covers_blocked_send_or_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        sender = _sender()
        monkeypatch.setattr(sender, "_ensure_recv_task", lambda: None)

        async def never_returns(*_args: Any, **_kwargs: Any) -> Any:
            await asyncio.Future()

        monkeypatch.setattr(sender, "_invoke_tl_once", never_returns)
        with pytest.raises(RpcSenderError, match="total deadline"):
            await sender.invoke_tl(object(), timeout=0.01)

    asyncio.run(run())


def test_flood_wait_cannot_extend_past_total_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def run() -> None:
        sender = _sender()
        monkeypatch.setattr(sender, "_ensure_recv_task", lambda: None)

        async def flood(*_args: Any, **_kwargs: Any) -> Any:
            return FloodWaitError(code=420, message="FLOOD_WAIT_10", wait_seconds=10)

        monkeypatch.setattr(sender, "_invoke_tl_once", flood)
        with pytest.raises(FloodWaitError) as raised:
            await sender.invoke_tl(object(), timeout=0.1)
        assert raised.value.wait_seconds == 10

    asyncio.run(run())
