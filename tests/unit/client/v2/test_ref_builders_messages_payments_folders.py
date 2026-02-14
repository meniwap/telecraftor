from __future__ import annotations

import pytest

from telecraft.client import (
    FolderAssignment,
    InvoiceRef,
    ReplyToMessageRef,
    ReplyToStoryRef,
    StarsAmountRef,
)


@pytest.mark.unit
def test_ref_builders_messages_payments_folders__constructors__work() -> None:
    folder = FolderAssignment.of("user:1", 2)
    invoice = InvoiceRef.by_message("user:1", 10)
    reply_msg = ReplyToMessageRef(11)
    reply_story = ReplyToStoryRef(peer="user:1", story_id=12)
    stars = StarsAmountRef(amount=5, nanos=1).to_tl()

    assert folder.folder_id == 2
    assert invoice.msg_id == 10
    assert reply_msg.msg_id == 11
    assert reply_story.story_id == 12
    assert int(stars.amount) == 5
