from __future__ import annotations

import asyncio
import time
from collections import deque

import pytest

from telecraft.bot.dispatcher import Dispatcher, _DispatchTaskPool, _TokenBucket
from telecraft.bot.events import MessageEvent
from telecraft.bot.router import Router


class _Client:
    def __init__(self) -> None:
        self.sent: list[tuple[object, str]] = []

    async def send_message(
        self,
        peer: object,
        text: str,
        *,
        reply_to_msg_id: int | None = None,
        reply_markup: object | None = None,
    ) -> object:
        _ = (reply_to_msg_id, reply_markup)
        self.sent.append((peer, text))
        return {"ok": True}


async def _wait_until(predicate, *, timeout: float = 1.0) -> None:
    async def _poll() -> None:
        while not predicate():
            await asyncio.sleep(0)

    await asyncio.wait_for(_poll(), timeout=timeout)


def test_dispatch_pool__queues_above_concurrency_limit_without_dropping() -> None:
    async def _case() -> tuple[bool, list[str]]:
        pool = _DispatchTaskPool(limit=1)
        first_started = asyncio.Event()
        release_first = asyncio.Event()
        ran: list[str] = []

        async def _first() -> None:
            ran.append("first")
            first_started.set()
            await release_first.wait()

        async def _second() -> None:
            ran.append("second")

        assert pool.schedule(_first, label="first", serial_key=("user", 1, 1)) is True
        await first_started.wait()
        queued = pool.schedule(_second, label="second", serial_key=("user", 2, 2))
        await asyncio.sleep(0)
        assert ran == ["first"]
        release_first.set()
        await _wait_until(lambda: ran == ["first", "second"])
        await pool.close()
        return queued, ran

    assert asyncio.run(_case()) == (True, ["first", "second"])


def test_dispatch_pool__bounds_pending_tasks_and_rate_limits_overflow_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def _case() -> tuple[bool, bool, bool, bool, int]:
        pool = _DispatchTaskPool(limit=1, max_pending=2)
        started = asyncio.Event()
        release = asyncio.Event()
        overflow_runs = 0

        async def _blocked() -> None:
            started.set()
            await release.wait()

        async def _queued() -> None:
            nonlocal overflow_runs
            overflow_runs += 1

        first = pool.schedule(_blocked, label="first", serial_key=("user", 1, 1))
        await started.wait()
        second = pool.schedule(_queued, label="second", serial_key=("user", 2, 2))
        overflow_one = pool.schedule(_queued, label="overflow-1", serial_key=("user", 3, 3))
        overflow_two = pool.schedule(_queued, label="overflow-2", serial_key=("user", 4, 4))
        release.set()
        await _wait_until(lambda: overflow_runs == 1)
        await pool.close()
        return first, second, overflow_one, overflow_two, overflow_runs

    with caplog.at_level("WARNING", logger="telecraft.bot.dispatcher"):
        assert asyncio.run(_case()) == (True, True, False, False, 1)
    matching = [
        record for record in caplog.records if "max pending handlers reached" in record.getMessage()
    ]
    assert len(matching) == 1


def test_dispatch_pool__rejects_invalid_limits() -> None:
    with pytest.raises(ValueError, match="max_concurrent_handlers"):
        _DispatchTaskPool(limit=0)
    with pytest.raises(ValueError, match="max_pending_handlers"):
        _DispatchTaskPool(limit=2, max_pending=1)


def test_dispatch_pool__cancelled_handler_does_not_cancel_sender_lane() -> None:
    async def _case() -> list[str]:
        pool = _DispatchTaskPool(limit=1)
        first_started = asyncio.Event()
        release_first = asyncio.Event()
        ran: list[str] = []

        async def _first() -> None:
            ran.append("first")
            first_started.set()
            await release_first.wait()
            raise asyncio.CancelledError

        async def _second() -> None:
            ran.append("second")

        key = ("channel", 10, 7)
        assert pool.schedule(_first, label="first", serial_key=key)
        await first_started.wait()
        assert pool.schedule(_second, label="second", serial_key=key)
        release_first.set()
        await _wait_until(lambda: ran == ["first", "second"])
        await pool.close()
        return ran

    assert asyncio.run(_case()) == ["first", "second"]


def test_dispatcher__ask_answer_bypasses_full_handler_pool() -> None:
    async def _case() -> tuple[list[str], list[str]]:
        client = _Client()
        router = Router()
        answers: list[str] = []

        @router.on_message(lambda event: event.text == "/settings")
        async def _settings(event: MessageEvent) -> None:
            answer = await router.ask(event, "question?", timeout=1.0, same_sender=True)
            answers.append(answer.text or "")
            await answer.reply("saved")

        dispatcher = Dispatcher(
            client=object(),
            router=router,
            ignore_before_start=False,
            max_concurrent_handlers=1,
        )
        pool = _DispatchTaskPool(limit=1)
        seen: set[tuple[str, int, int, str]] = set()
        seen_order: deque[tuple[str, int, int, str]] = deque(maxlen=4096)
        peer_buckets = {}
        started_at = int(time.time())

        trigger = MessageEvent(
            client=client,
            raw=object(),
            peer_type="channel",
            peer_id=10,
            sender_id=7,
            msg_id=1,
            text="/settings",
        )
        await dispatcher._handle_message(
            trigger,
            started_at,
            seen,
            seen_order,
            None,
            None,
            peer_buckets,
            pool,
        )
        await asyncio.sleep(0)

        answer = MessageEvent(
            client=client,
            raw=object(),
            peer_type="channel",
            peer_id=10,
            sender_id=7,
            msg_id=2,
            text="readonly off",
        )
        await dispatcher._handle_message(
            answer,
            started_at,
            seen,
            seen_order,
            None,
            None,
            peer_buckets,
            pool,
        )

        for _ in range(10):
            if answers:
                break
            await asyncio.sleep(0)
        await pool.close()
        return answers, [text for _peer, text in client.sent]

    answers, sent = asyncio.run(_case())
    assert answers == ["readonly off"]
    assert sent == ["question?", "saved"]


def test_dispatcher__answer_ingested_before_waiter_is_not_stuck_in_sender_lane() -> None:
    async def _case() -> tuple[list[str], list[str]]:
        client = _Client()
        router = Router()
        before_ask = asyncio.Event()
        allow_ask = asyncio.Event()
        answers: list[str] = []
        ordinary: list[str] = []

        @router.on_message(lambda event: event.text == "/settings", stop=True)
        async def _settings(event: MessageEvent) -> None:
            before_ask.set()
            await allow_ask.wait()
            answer = await router.ask(event, "question?", timeout=1.0, same_sender=True)
            answers.append(answer.text or "")

        @router.on_message()
        async def _ordinary(event: MessageEvent) -> None:
            ordinary.append(event.text or "")

        dispatcher = Dispatcher(
            client=object(),
            router=router,
            ignore_before_start=False,
            max_concurrent_handlers=2,
        )
        router.open_conversations()
        pool = _DispatchTaskPool(limit=2)
        seen: set[tuple[str, int, int, str]] = set()
        seen_order: deque[tuple[str, int, int, str]] = deque(maxlen=4096)
        peer_buckets = {}
        started_at = int(time.time())

        async def _send(msg_id: int, text: str) -> None:
            await dispatcher._handle_message(
                MessageEvent(
                    client=client,
                    raw=object(),
                    peer_type="channel",
                    peer_id=10,
                    sender_id=7,
                    msg_id=msg_id,
                    text=text,
                ),
                started_at,
                seen,
                seen_order,
                None,
                None,
                peer_buckets,
                pool,
            )

        await _send(1, "/settings")
        await before_ask.wait()
        await _send(2, "readonly on")
        allow_ask.set()
        await _wait_until(lambda: answers == ["readonly on"])
        router.close_conversations()
        await pool.close()
        router.clear_buffered_conversations()
        return answers, ordinary

    assert asyncio.run(_case()) == (["readonly on"], [])


def test_dispatcher__rapid_messages_in_same_peer_remain_serial() -> None:
    async def _case() -> tuple[list[tuple[int | None, int | None]], list[str]]:
        client = _Client()
        router = Router()
        answers: list[tuple[int | None, int | None]] = []

        @router.on_message(lambda event: event.text == "/settings")
        async def _settings(event: MessageEvent) -> None:
            answer = await router.ask(event, "question?", timeout=1.0, same_sender=True)
            answers.append((event.msg_id, answer.msg_id))

        dispatcher = Dispatcher(
            client=object(),
            router=router,
            ignore_before_start=False,
            max_concurrent_handlers=4,
        )
        pool = _DispatchTaskPool(limit=4)
        seen: set[tuple[str, int, int, str]] = set()
        seen_order: deque[tuple[str, int, int, str]] = deque(maxlen=4096)
        peer_buckets = {}
        started_at = int(time.time())

        def _message(msg_id: int, text: str) -> MessageEvent:
            return MessageEvent(
                client=client,
                raw=object(),
                peer_type="channel",
                peer_id=10,
                sender_id=7,
                msg_id=msg_id,
                text=text,
            )

        # Both commands are ingested before either dispatch task gets CPU time.
        for event in (_message(1, "/settings"), _message(2, "/settings")):
            await dispatcher._handle_message(
                event,
                started_at,
                seen,
                seen_order,
                None,
                None,
                peer_buckets,
                pool,
            )

        await _wait_until(lambda: len(client.sent) == 1)
        assert answers == []

        await dispatcher._handle_message(
            _message(3, "first answer"),
            started_at,
            seen,
            seen_order,
            None,
            None,
            peer_buckets,
            pool,
        )
        await _wait_until(lambda: len(answers) == 1 and len(client.sent) == 2)

        await dispatcher._handle_message(
            _message(4, "second answer"),
            started_at,
            seen,
            seen_order,
            None,
            None,
            peer_buckets,
            pool,
        )
        await _wait_until(lambda: len(answers) == 2)
        await pool.close()
        return answers, [text for _peer, text in client.sent]

    answers, sent = asyncio.run(_case())
    assert answers == [(1, 3), (2, 4)]
    assert sent == ["question?", "question?"]


def test_dispatcher__conversation_does_not_block_other_group_sender() -> None:
    async def _case() -> tuple[list[str], list[str]]:
        client = _Client()
        router = Router()
        answers: list[str] = []
        ordinary: list[str] = []

        @router.on_message(lambda event: event.text == "/settings", stop=True)
        async def _settings(event: MessageEvent) -> None:
            answer = await router.ask(event, "question?", timeout=1.0, same_sender=True)
            answers.append(answer.text or "")

        @router.on_message()
        async def _ordinary(event: MessageEvent) -> None:
            ordinary.append(event.text or "")

        dispatcher = Dispatcher(
            client=object(),
            router=router,
            ignore_before_start=False,
            max_concurrent_handlers=2,
        )
        pool = _DispatchTaskPool(limit=2)
        seen: set[tuple[str, int, int, str]] = set()
        seen_order: deque[tuple[str, int, int, str]] = deque(maxlen=4096)
        peer_buckets = {}
        started_at = int(time.time())

        async def _send(msg_id: int, sender_id: int, text: str) -> None:
            await dispatcher._handle_message(
                MessageEvent(
                    client=client,
                    raw=object(),
                    peer_type="channel",
                    peer_id=10,
                    sender_id=sender_id,
                    msg_id=msg_id,
                    text=text,
                ),
                started_at,
                seen,
                seen_order,
                None,
                None,
                peer_buckets,
                pool,
            )

        await _send(1, 7, "/settings")
        await _wait_until(lambda: len(client.sent) == 1)
        await _send(2, 8, "ordinary message")
        await _wait_until(lambda: ordinary == ["ordinary message"])
        await _send(3, 7, "readonly on")
        await _wait_until(lambda: answers == ["readonly on"])
        await pool.close()
        return answers, ordinary

    assert asyncio.run(_case()) == (["readonly on"], ["ordinary message"])


def test_dispatcher__sleep_throttle_staggers_concurrent_peers() -> None:
    async def _case() -> list[float]:
        router = Router()
        dispatch_times: list[float] = []
        all_dispatched = asyncio.Event()

        @router.on_message()
        async def _capture(_event: MessageEvent) -> None:
            dispatch_times.append(time.monotonic())
            if len(dispatch_times) == 4:
                all_dispatched.set()

        dispatcher = Dispatcher(
            client=object(),
            router=router,
            ignore_before_start=False,
            throttle_max_delay_seconds=0.03,
            max_concurrent_handlers=8,
        )
        pool = _DispatchTaskPool(limit=8)
        throttle_lock = asyncio.Lock()
        global_bucket = _TokenBucket(
            rate_per_sec=20.0,
            capacity=1.0,
            tokens=1.0,
            last_refill=time.monotonic(),
        )
        seen: set[tuple[str, int, int, str]] = set()
        seen_order: deque[tuple[str, int, int, str]] = deque(maxlen=4096)
        peer_buckets = {}
        started_at = int(time.time())

        for msg_id in range(1, 5):
            await dispatcher._handle_message(
                MessageEvent(
                    client=object(),
                    raw=object(),
                    peer_type="user",
                    peer_id=msg_id,
                    msg_id=msg_id,
                    text=str(msg_id),
                ),
                started_at,
                seen,
                seen_order,
                global_bucket,
                None,
                peer_buckets,
                pool,
                throttle_lock,
            )

        await asyncio.wait_for(all_dispatched.wait(), timeout=1.0)
        await pool.close()
        return dispatch_times

    dispatch_times = asyncio.run(_case())
    gaps = [right - left for left, right in zip(dispatch_times, dispatch_times[1:])]
    assert len(dispatch_times) == 4
    assert all(gap >= 0.015 for gap in gaps)
