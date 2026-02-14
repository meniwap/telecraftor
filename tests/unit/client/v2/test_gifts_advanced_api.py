from __future__ import annotations

import pytest

from telecraft.client import Client


class _Raw:
    pass


@pytest.mark.unit
def test_gifts_advanced_api__subclients__available() -> None:
    client = Client(raw=_Raw())
    assert hasattr(client.gifts.saved, "set_resale_price")
    assert hasattr(client.gifts, "notifications")
    assert hasattr(client.gifts.notifications, "toggle_chat")
    assert hasattr(client.gifts, "collections")
