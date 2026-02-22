from __future__ import annotations

from telecraft.client import Client


class _Raw:
    is_connected = False


def test_bots__namespace__returns_expected_shape() -> None:
    client = Client(raw=_Raw())
    assert hasattr(client, "bots")


def test_bots__set_commands__returns_expected_shape() -> None:
    client = Client(raw=_Raw())
    assert hasattr(client.bots, "set_commands")
