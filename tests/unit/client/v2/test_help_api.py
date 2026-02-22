from __future__ import annotations

from telecraft.client import Client


class _Raw:
    is_connected = False


def test_help__namespace__returns_expected_shape() -> None:
    client = Client(raw=_Raw())
    assert hasattr(client, "help")


def test_help__config__returns_expected_shape() -> None:
    client = Client(raw=_Raw())
    assert hasattr(client.help, "config")
