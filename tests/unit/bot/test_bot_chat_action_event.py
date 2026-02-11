from __future__ import annotations

import asyncio
from dataclasses import dataclass

from telecraft.bot import Router, action_join
from telecraft.bot.events import ChatActionEvent, MessageEvent, parse_events


@dataclass
class FakePeerChat:
    TL_NAME = "peerChat"

    chat_id: int


@dataclass
class FakePeerUser:
    TL_NAME = "peerUser"

    user_id: int


@dataclass
class FakeActionChatAddUser:
    TL_NAME = "messageActionChatAddUser"

    users: list[int]


@dataclass
class FakeActionChatJoinedByRequest:
    TL_NAME = "messageActionChatJoinedByRequest"


@dataclass
class FakeActionChatJoinedByLink:
    TL_NAME = "messageActionChatJoinedByLink"

    inviter_id: int


@dataclass
class FakeReplyHeader:
    reply_to_msg_id: int


@dataclass
class FakeActionPinMessage:
    TL_NAME = "messageActionPinMessage"


@dataclass
class FakeMessageService:
    TL_NAME = "messageService"

    flags: int
    id: int
    date: int
    peer_id: object
    from_id: object | None
    action: object
    reply_to: object | None = None


def test_chat_action_from_message_service_join() -> None:
    msg = FakeMessageService(
        flags=0,
        id=10,
        date=1_700_000_000,
        peer_id=FakePeerChat(chat_id=123),
        from_id=FakePeerUser(user_id=5),
        action=FakeActionChatAddUser(users=[111, 222]),
    )
    e = ChatActionEvent.from_update(client=object(), update=msg)
    assert e is not None
    assert e.kind == "join"
    assert e.peer_type == "chat"
    assert e.peer_id == 123
    assert e.sender_id == 5
    assert e.added_user_ids == [111, 222]


def test_chat_action_from_message_service_join_by_request() -> None:
    msg = FakeMessageService(
        flags=0,
        id=11,
        date=1_700_000_000,
        peer_id=FakePeerChat(chat_id=123),
        from_id=FakePeerUser(user_id=5),
        action=FakeActionChatJoinedByRequest(),
    )
    e = ChatActionEvent.from_update(client=object(), update=msg)
    assert e is not None
    assert e.kind == "join"


def test_chat_action_from_message_service_join_by_link_has_inviter_id() -> None:
    msg = FakeMessageService(
        flags=0,
        id=12,
        date=1_700_000_000,
        peer_id=FakePeerChat(chat_id=123),
        from_id=FakePeerUser(user_id=5),
        action=FakeActionChatJoinedByLink(inviter_id=999),
    )
    e = ChatActionEvent.from_update(client=object(), update=msg)
    assert e is not None
    assert e.kind == "join"
    assert e.inviter_id == 999


def test_chat_action_pin_reads_pinned_msg_id_from_reply_header() -> None:
    msg = FakeMessageService(
        flags=0,
        id=13,
        date=1_700_000_000,
        peer_id=FakePeerChat(chat_id=123),
        from_id=FakePeerUser(user_id=5),
        action=FakeActionPinMessage(),
        reply_to=FakeReplyHeader(reply_to_msg_id=77),
    )
    e = ChatActionEvent.from_update(client=object(), update=msg)
    assert e is not None
    assert e.kind == "pin"
    assert e.pinned_msg_id == 77


def test_parse_events_prefers_chat_action_over_message_event_for_message_service() -> None:
    msg = FakeMessageService(
        flags=0,
        id=10,
        date=1_700_000_000,
        peer_id=FakePeerChat(chat_id=123),
        from_id=FakePeerUser(user_id=5),
        action=FakeActionChatAddUser(users=[111]),
    )
    evts = parse_events(client=object(), update=msg)
    assert any(isinstance(e, ChatActionEvent) for e in evts)
    assert not any(isinstance(e, MessageEvent) for e in evts)


def test_router_on_action_dispatches() -> None:
    msg = FakeMessageService(
        flags=0,
        id=10,
        date=1_700_000_000,
        peer_id=FakePeerChat(chat_id=123),
        from_id=FakePeerUser(user_id=5),
        action=FakeActionChatAddUser(users=[111]),
    )
    evt = ChatActionEvent.from_update(client=object(), update=msg)
    assert evt is not None

    got: list[str] = []
    r = Router()

    @r.on_action(action_join())
    async def _h(e: ChatActionEvent) -> None:
        got.append(f"{e.kind}:{e.peer_type}:{e.peer_id}")

    asyncio.run(r.dispatch_action(evt))
    assert got == ["join:chat:123"]
