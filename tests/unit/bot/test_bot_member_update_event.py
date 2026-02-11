from __future__ import annotations

import asyncio
from dataclasses import dataclass

from telecraft.bot import Router, member_banned, member_joined, member_promoted
from telecraft.bot.events import MemberUpdateEvent, parse_events


@dataclass
class FakeChatParticipant:
    TL_NAME = "chatParticipant"


@dataclass
class FakeChatParticipantAdmin:
    TL_NAME = "chatParticipantAdmin"


@dataclass
class FakeChannelParticipant:
    TL_NAME = "channelParticipant"


@dataclass
class FakeChannelParticipantBanned:
    TL_NAME = "channelParticipantBanned"

    left: bool = False


@dataclass
class FakeUpdateChatParticipant:
    TL_NAME = "updateChatParticipant"

    chat_id: int
    date: int
    actor_id: int
    user_id: int
    prev_participant: object | None = None
    new_participant: object | None = None
    invite: object | None = None
    qts: int = 1


@dataclass
class FakeUpdateChannelParticipant:
    TL_NAME = "updateChannelParticipant"

    channel_id: int
    date: int
    actor_id: int
    user_id: int
    via_chatlist: bool = False
    prev_participant: object | None = None
    new_participant: object | None = None
    invite: object | None = None
    qts: int = 1


def test_member_update_join_vs_invite() -> None:
    upd_join = FakeUpdateChatParticipant(
        chat_id=10,
        date=1_700_000_000,
        actor_id=123,
        user_id=123,
        prev_participant=None,
        new_participant=FakeChatParticipant(),
        qts=10,
    )
    e = MemberUpdateEvent.from_update(client=object(), update=upd_join)
    assert e is not None
    assert e.peer_type == "chat"
    assert e.peer_id == 10
    assert e.kind == "join"

    upd_inv = FakeUpdateChatParticipant(
        chat_id=10,
        date=1_700_000_000,
        actor_id=999,
        user_id=123,
        prev_participant=None,
        new_participant=FakeChatParticipant(),
        qts=11,
    )
    e2 = MemberUpdateEvent.from_update(client=object(), update=upd_inv)
    assert e2 is not None
    assert e2.kind == "invite"


def test_member_update_promote() -> None:
    upd = FakeUpdateChatParticipant(
        chat_id=10,
        date=1_700_000_000,
        actor_id=999,
        user_id=123,
        prev_participant=FakeChatParticipant(),
        new_participant=FakeChatParticipantAdmin(),
        qts=12,
    )
    e = MemberUpdateEvent.from_update(client=object(), update=upd)
    assert e is not None
    assert e.kind == "promote"


def test_member_update_channel_ban_vs_left() -> None:
    upd_ban = FakeUpdateChannelParticipant(
        channel_id=5,
        date=1_700_000_000,
        actor_id=9,
        user_id=7,
        prev_participant=FakeChannelParticipant(),
        new_participant=FakeChannelParticipantBanned(left=False),
        qts=13,
    )
    e = MemberUpdateEvent.from_update(client=object(), update=upd_ban)
    assert e is not None
    assert e.peer_type == "channel"
    assert e.peer_id == 5
    assert e.kind == "ban"

    upd_left = FakeUpdateChannelParticipant(
        channel_id=5,
        date=1_700_000_000,
        actor_id=7,
        user_id=7,
        prev_participant=FakeChannelParticipant(),
        new_participant=FakeChannelParticipantBanned(left=True),
        qts=14,
    )
    e2 = MemberUpdateEvent.from_update(client=object(), update=upd_left)
    assert e2 is not None
    assert e2.kind == "leave"


def test_parse_events_emits_member_update_event() -> None:
    upd = FakeUpdateChatParticipant(
        chat_id=10,
        date=1_700_000_000,
        actor_id=123,
        user_id=123,
        new_participant=FakeChatParticipant(),
        qts=15,
    )
    evts = parse_events(client=object(), update=upd)
    assert any(isinstance(x, MemberUpdateEvent) for x in evts)


def test_router_on_member_update_dispatches_with_filters() -> None:
    upd = FakeUpdateChatParticipant(
        chat_id=10,
        date=1_700_000_000,
        actor_id=999,
        user_id=123,
        prev_participant=FakeChatParticipant(),
        new_participant=FakeChatParticipantAdmin(),
        qts=16,
    )
    evt = MemberUpdateEvent.from_update(client=object(), update=upd)
    assert evt is not None

    got: list[str] = []
    r = Router()

    @r.on_member_update(member_promoted())
    async def _h(e: MemberUpdateEvent) -> None:
        got.append(f"{e.kind}:{e.peer_type}:{e.peer_id}:{e.user_id}")

    asyncio.run(r.dispatch_member_update(evt))
    assert got == ["promote:chat:10:123"]


def test_member_filters_joined_and_banned() -> None:
    join_evt = MemberUpdateEvent(
        client=object(),
        raw=object(),
        peer_type="chat",
        peer_id=1,
        date=1,
        actor_id=1,
        user_id=1,
        kind="join",
    )
    assert member_joined()(join_evt) is True

    ban_evt = MemberUpdateEvent(
        client=object(),
        raw=object(),
        peer_type="channel",
        peer_id=1,
        date=1,
        actor_id=2,
        user_id=3,
        kind="ban",
    )
    assert member_banned()(ban_evt) is True


