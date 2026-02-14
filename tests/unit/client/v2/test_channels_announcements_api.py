from __future__ import annotations

import pytest

from telecraft.client import Client


class _Raw:
    pass


@pytest.mark.unit
def test_channels_announcements_api__subclients__available() -> None:
    client = Client(raw=_Raw())
    assert hasattr(client.channels.settings, "restrict_sponsored")
    assert callable(client.channels.search_posts)
    assert hasattr(client.channels.search_posts, "check_flood")
