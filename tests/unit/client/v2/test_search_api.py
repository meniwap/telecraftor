from __future__ import annotations

from telecraft.client import Client


class _Raw:
    is_connected = False


def test_search__global_messages__returns_expected_shape() -> None:
    client = Client(raw=_Raw())
    assert hasattr(client.search, "global_messages")


def test_search__discussion_replies__returns_expected_shape() -> None:
    client = Client(raw=_Raw())
    assert hasattr(client.search, "discussion_replies")
