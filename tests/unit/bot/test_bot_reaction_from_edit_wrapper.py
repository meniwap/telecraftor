from __future__ import annotations

from dataclasses import dataclass

from telecraft.bot.events import ReactionEvent


@dataclass
class FakePeerUser:
    TL_NAME = "peerUser"
    user_id: int


@dataclass
class FakeMessage:
    TL_NAME = "message"
    id: int
    peer_id: object
    reactions: object | None = None


@dataclass
class FakeUpdateEditMessage:
    TL_NAME = "updateEditMessage"
    message: object


def test_reaction_event_can_be_built_from_edit_wrapper() -> None:
    m = FakeMessage(id=10, peer_id=FakePeerUser(user_id=1), reactions=object())
    upd = FakeUpdateEditMessage(message=m)
    e = ReactionEvent.from_update(client=object(), update=upd)
    assert e is not None
    assert e.peer_type == "user"
    assert e.peer_id == 1
    assert e.msg_id == 10
