from __future__ import annotations

import asyncio
from collections import deque

from telecraft.bot.dispatcher import Dispatcher
from telecraft.bot.events import CallbackQueryEvent
from telecraft.bot.router import Router


def _event(*, query_id: int, data: bytes = b"x") -> CallbackQueryEvent:
    return CallbackQueryEvent(
        client=object(),
        raw=object(),
        query_id=query_id,
        user_id=1,
        peer_type="chat",
        peer_id=10,
        msg_id=11,
        inline_msg_id=None,
        data=data,
        game_short_name=None,
        chat_instance=12,
    )


def test_dispatcher_callback_dedupe__drops_duplicate_query_id() -> None:
    seen_ids: list[int] = []
    router = Router()

    @router.on_callback_query()
    async def _h(e: CallbackQueryEvent) -> None:
        seen_ids.append(int(e.query_id))

    disp = Dispatcher(client=object(), router=router, ignore_before_start=False)

    async def _run() -> None:
        seen_other: set[tuple[str, str, int, int]] = set()
        seen_other_order: deque[tuple[str, str, int, int]] = deque(maxlen=4096)
        await disp._handle_callback(  # noqa: SLF001
            _event(query_id=777, data=b"a"),
            started_at=0,
            now_ts=999999999,
            seen_other=seen_other,
            seen_other_order=seen_other_order,
            global_bucket=None,
            peer_rate_per_sec=None,
            peer_buckets={},
        )
        await disp._handle_callback(  # noqa: SLF001
            _event(query_id=777, data=b"b"),
            started_at=0,
            now_ts=999999999,
            seen_other=seen_other,
            seen_other_order=seen_other_order,
            global_bucket=None,
            peer_rate_per_sec=None,
            peer_buckets={},
        )

    asyncio.run(_run())
    assert seen_ids == [777]


def test_dispatcher_callback_dedupe__process_no_reply_marks_event() -> None:
    seen: list[tuple[bool, bool]] = []
    router = Router()

    @router.on_callback_query()
    async def _h(e: CallbackQueryEvent) -> None:
        seen.append((bool(e.is_backlog), bool(e.allow_reply)))

    disp = Dispatcher(
        client=object(),
        router=router,
        ignore_before_start=True,
        backlog_policy="process_no_reply",
        backlog_grace_seconds=60,
    )

    async def _run() -> None:
        seen_other: set[tuple[str, str, int, int]] = set()
        seen_other_order: deque[tuple[str, str, int, int]] = deque(maxlen=4096)
        await disp._handle_callback(  # noqa: SLF001
            _event(query_id=888),
            started_at=100,
            now_ts=100,
            seen_other=seen_other,
            seen_other_order=seen_other_order,
            global_bucket=None,
            peer_rate_per_sec=None,
            peer_buckets={},
        )

    asyncio.run(_run())
    assert seen == [(True, False)]
