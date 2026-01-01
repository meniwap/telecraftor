from __future__ import annotations

from telecraft.bot.dispatcher import Dispatcher
from telecraft.bot.events import MessageEvent, ReactionEvent
from telecraft.bot.router import Router


def test_dispatcher_backlog_policy_process_no_reply_sets_flags() -> None:
    disp = Dispatcher(
        client=object(),
        router=Router(),
        ignore_before_start=True,
        backlog_grace_seconds=10,
        backlog_policy="process_no_reply",
    )
    evt = MessageEvent(client=object(), raw=object(), date=0, msg_id=1, peer_type="user", peer_id=1)
    ok = disp._apply_backlog_policy(evt, started_at=1000)  # noqa: SLF001
    assert ok is True
    assert evt.is_backlog is True
    assert evt.allow_reply is False


def test_dispatcher_backlog_policy_ignore_drops() -> None:
    disp = Dispatcher(
        client=object(),
        router=Router(),
        ignore_before_start=True,
        backlog_grace_seconds=10,
        backlog_policy="ignore",
    )
    evt = MessageEvent(client=object(), raw=object(), date=0, msg_id=1, peer_type="user", peer_id=1)
    ok = disp._apply_backlog_policy(evt, started_at=1000)  # noqa: SLF001
    assert ok is False


def test_dispatcher_backlog_policy_marks_undated_events_at_startup() -> None:
    disp = Dispatcher(
        client=object(),
        router=Router(),
        ignore_before_start=True,
        backlog_grace_seconds=2,
        backlog_policy="process_no_reply",
    )
    evt = ReactionEvent(
        client=object(),
        raw=object(),
        peer_type="chat",
        peer_id=1,
        msg_id=1,
        reactions=None,
    )
    ok = disp._apply_backlog_policy(evt, started_at=1000, now_ts=1001)  # noqa: SLF001
    assert ok is True
    assert evt.is_backlog is True


