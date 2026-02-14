from __future__ import annotations

import pytest

from telecraft.client import Client


class _Raw:
    pass


@pytest.mark.unit
def test_messages_extended__subclients__available() -> None:
    client = Client(raw=_Raw())
    assert hasattr(client.messages, "web")
    assert hasattr(client.messages, "discussion")
    assert hasattr(client.messages, "receipts")
    assert hasattr(client.messages, "effects")
    assert hasattr(client.messages, "sent_media")
    assert hasattr(client.messages, "gifs")
    assert hasattr(client.messages, "paid_reactions")
    assert hasattr(client.messages, "inline")
    assert hasattr(client.messages, "history_import")
