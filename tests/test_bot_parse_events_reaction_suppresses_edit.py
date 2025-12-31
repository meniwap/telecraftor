from __future__ import annotations

from dataclasses import dataclass

from telecraft.bot.events import ReactionEvent, parse_events


@dataclass
class FakePeerUser:
    TL_NAME = "peerUser"
    user_id: int


@dataclass
class FakeMessage:
    TL_NAME = "message"
    flags: int
    id: int
    date: int
    message: bytes
    peer_id: object
    reactions: object | None = None
    # No edit_date field -> should be treated as reaction-only edit.


@dataclass
class FakeUpdateEditMessage:
    TL_NAME = "updateEditMessage"
    message: object


def test_parse_events_prefers_reaction_over_edit_when_no_edit_date() -> None:
    m = FakeMessage(
        flags=0,
        id=10,
        date=1_700_000_000,
        message=b"hi",
        peer_id=FakePeerUser(user_id=1),
        reactions=object(),
    )
    upd = FakeUpdateEditMessage(message=m)
    evts = parse_events(client=object(), update=upd)
    assert any(isinstance(e, ReactionEvent) for e in evts)
    # Should not include MessageEvent(kind="edit") for reaction-only edits.
    assert all(getattr(e, "kind", None) != "edit" for e in evts)


