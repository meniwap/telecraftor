from __future__ import annotations

import asyncio
from dataclasses import dataclass

from telecraft.bot.dispatcher import Dispatcher
from telecraft.bot.events import ChatActionEvent
from telecraft.bot.router import Router


@dataclass
class _CaptureRouter(Router):
    seen: list[ChatActionEvent]


def test_action_dedupe_does_not_drop_legit_repeated_pins_with_different_msg_id() -> None:
    seen: list[ChatActionEvent] = []
    router = Router()

    @router.on_action()
    async def _h(e: ChatActionEvent) -> None:
        seen.append(e)

    disp = Dispatcher(client=object(), router=router, ignore_before_start=False)

    async def _run() -> None:
        # Minimal sets required by _handle_action.
        msg_seen: set[tuple[str, int, int, str]] = set()
        msg_order = __import__("collections").deque(maxlen=4096)
        sig_seen: set[tuple[str, int, str, str, int]] = set()
        sig_order = __import__("collections").deque(maxlen=4096)

        e1 = ChatActionEvent(
            client=object(),
            raw=object(),
            peer_type="chat",
            peer_id=1,
            msg_id=100,
            date=1_700_000_000,
            sender_id=1,
            outgoing=False,
            kind="pin",
            action_name="messageActionPinMessage",
            pinned_msg_id=77,
        )
        e2 = ChatActionEvent(
            client=object(),
            raw=object(),
            peer_type="chat",
            peer_id=1,
            msg_id=101,
            date=1_700_000_001,
            sender_id=1,
            outgoing=False,
            kind="pin",
            action_name="messageActionPinMessage",
            pinned_msg_id=77,
        )

        await disp._handle_action(  # noqa: SLF001
            e1,
            0,
            msg_seen,
            msg_order,
            sig_seen,
            sig_order,
            None,
            None,
            {},
        )
        await disp._handle_action(  # noqa: SLF001
            e2,
            0,
            msg_seen,
            msg_order,
            sig_seen,
            sig_order,
            None,
            None,
            {},
        )

    asyncio.run(_run())
    assert [e.msg_id for e in seen] == [100, 101]


