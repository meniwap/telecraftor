from __future__ import annotations

import pytest

from telecraft.client import Client


class _Raw:
    pass


@pytest.mark.unit
def test_channels_discovery_growth__subclients__available() -> None:
    client = Client(raw=_Raw())
    assert hasattr(client.channels.settings, "toggle_join_to_send")
    assert hasattr(client.channels, "search_posts")
    assert hasattr(client.discovery.channels, "left")
    assert hasattr(client.discovery.bots, "popular_apps")
