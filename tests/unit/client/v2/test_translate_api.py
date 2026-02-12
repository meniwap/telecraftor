from __future__ import annotations

from telecraft.client import Client


class _Raw:
    is_connected = False


def test_translate__text__returns_expected_shape() -> None:
    client = Client(raw=_Raw())
    assert hasattr(client.translate, "text")


def test_translate__messages__returns_expected_shape() -> None:
    client = Client(raw=_Raw())
    assert hasattr(client.translate, "messages")
