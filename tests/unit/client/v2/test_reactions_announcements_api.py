from __future__ import annotations

import pytest

from telecraft.client import Client


class _Raw:
    pass


@pytest.mark.unit
def test_reactions_announcements_api__subclients__available() -> None:
    client = Client(raw=_Raw())
    assert hasattr(client.reactions, "defaults")
    assert hasattr(client.reactions, "chat")
    assert hasattr(client.reactions, "recent")
