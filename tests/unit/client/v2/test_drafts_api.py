from __future__ import annotations

from telecraft.client import Client


class _Raw:
    is_connected = False


def test_drafts__list__returns_expected_shape() -> None:
    client = Client(raw=_Raw())
    assert hasattr(client.drafts, "list")


def test_drafts__save__returns_expected_shape() -> None:
    client = Client(raw=_Raw())
    assert hasattr(client.drafts, "save")
