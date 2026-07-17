from __future__ import annotations

from dataclasses import dataclass

from telecraft.bot.events import MessageEvent


@dataclass
class FakeUpdateShortMessage:
    TL_NAME = "updateShortMessage"

    flags: int
    out: bool  # simulate buggy field (may be True even when flags=0)
    user_id: int
    id: int
    date: int
    message: bytes


def test_outgoing_is_derived_from_flags_not_out_field() -> None:
    upd = FakeUpdateShortMessage(
        flags=0,
        out=True,  # should be ignored
        user_id=123,
        id=1,
        date=1_700_000_000,
        message=b"hi",
    )
    e = MessageEvent.from_update(client=object(), update=upd)
    assert e is not None
    assert e.outgoing is False


@dataclass
class FakePeerUser:
    TL_NAME = "peerUser"

    user_id: int


@dataclass
class FakeMessage:
    TL_NAME = "message"

    flags: int
    peer_id: object
    from_id: object | None
    id: int
    date: int
    message: bytes


class FakeClientWithSelf:
    def __init__(self, self_user_id: int) -> None:
        self.self_user_id = self_user_id


# Synthetic IDs: these tests must not embed identifiers from live Telegram accounts.
BOT_ID = 200_002
SENDER_ID = 100_001


def test_incoming_dm_with_from_id_is_not_outgoing() -> None:
    # A DM arriving at a bot session, with from_id present and out flag unset.
    upd = FakeMessage(
        flags=0,
        peer_id=FakePeerUser(user_id=SENDER_ID),
        from_id=FakePeerUser(user_id=SENDER_ID),
        id=10,
        date=1_700_000_000,
        message=b"hello bot",
    )
    e = MessageEvent.from_update(client=FakeClientWithSelf(BOT_ID), update=upd)
    assert e is not None
    assert e.outgoing is False
    assert e.sender_id == SENDER_ID


def test_incoming_dm_without_from_id_is_not_outgoing() -> None:
    # Telegram omits from_id when the sender IS the dialog peer — the normal
    # shape of an incoming DM. This must not be misread as self-authored.
    upd = FakeMessage(
        flags=0,
        peer_id=FakePeerUser(user_id=SENDER_ID),
        from_id=None,
        id=11,
        date=1_700_000_000,
        message=b"hello bot",
    )
    e = MessageEvent.from_update(client=FakeClientWithSelf(BOT_ID), update=upd)
    assert e is not None
    assert e.outgoing is False
    assert e.sender_id == SENDER_ID


def test_saved_messages_without_from_id_stays_outgoing() -> None:
    # Saved Messages: dialog peer is our own user id -> self-authored.
    upd = FakeMessage(
        flags=0,
        peer_id=FakePeerUser(user_id=BOT_ID),
        from_id=None,
        id=12,
        date=1_700_000_000,
        message=b"note to self",
    )
    e = MessageEvent.from_update(client=FakeClientWithSelf(BOT_ID), update=upd)
    assert e is not None
    assert e.outgoing is True


def test_private_message_without_from_id_and_unknown_self_keeps_legacy_outgoing() -> None:
    # Without self identity we keep the legacy assumption (self-authored) so
    # Saved Messages userbots keep working before get_me() has run.
    upd = FakeMessage(
        flags=0,
        peer_id=FakePeerUser(user_id=SENDER_ID),
        from_id=None,
        id=13,
        date=1_700_000_000,
        message=b"hi",
    )
    e = MessageEvent.from_update(client=object(), update=upd)
    assert e is not None
    assert e.outgoing is True
