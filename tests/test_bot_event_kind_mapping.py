from __future__ import annotations

from dataclasses import dataclass

from telecraft.bot.events import MessageEvent


@dataclass
class FakeMessage:
    TL_NAME = "message"

    flags: int
    id: int
    date: int
    message: bytes
    peer_id: object
    from_id: object | None = None
    media: object | None = None
    reply_to: object | None = None


@dataclass
class FakePeerUser:
    TL_NAME = "peerUser"

    user_id: int


@dataclass
class FakeUpdateWrapper:
    TL_NAME: str
    message: object


def test_update_edit_wrapper_sets_kind_edit() -> None:
    m = FakeMessage(
        flags=0,
        id=1,
        date=1_700_000_000,
        message=b"hi",
        peer_id=FakePeerUser(user_id=123),
    )
    upd = FakeUpdateWrapper(TL_NAME="updateEditMessage", message=m)
    e = MessageEvent.from_update(client=object(), update=upd)
    assert e is not None
    assert e.kind == "edit"


def test_update_new_wrapper_sets_kind_new() -> None:
    m = FakeMessage(
        flags=0,
        id=1,
        date=1_700_000_000,
        message=b"hi",
        peer_id=FakePeerUser(user_id=123),
    )
    upd = FakeUpdateWrapper(TL_NAME="updateNewMessage", message=m)
    e = MessageEvent.from_update(client=object(), update=upd)
    assert e is not None
    assert e.kind == "new"


