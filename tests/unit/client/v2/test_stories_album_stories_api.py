from __future__ import annotations

import pytest

from telecraft.client import Client


class _Raw:
    pass


@pytest.mark.unit
def test_stories_album_stories_api__method__available() -> None:
    client = Client(raw=_Raw())
    assert hasattr(client.stories.albums, "stories")
