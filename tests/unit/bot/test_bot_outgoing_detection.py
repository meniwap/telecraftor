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
