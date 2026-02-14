from __future__ import annotations

import pytest

from telecraft.client import Client


class _Raw:
    pass


@pytest.mark.unit
def test_stories_advanced_api__subclients__available() -> None:
    client = Client(raw=_Raw())
    assert hasattr(client.stories, "links")
    assert hasattr(client.stories, "views")
    assert hasattr(client.stories, "reactions")
    assert hasattr(client.stories, "stealth")
    assert hasattr(client.stories, "peers")
    assert hasattr(client.stories, "albums")
