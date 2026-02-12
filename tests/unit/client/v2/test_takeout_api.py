from __future__ import annotations

from telecraft.client import Client


class _Raw:
    is_connected = False


def test_takeout__start__returns_expected_shape() -> None:
    client = Client(raw=_Raw())
    assert hasattr(client.takeout, "start")


def test_takeout_messages__export__returns_expected_shape() -> None:
    client = Client(raw=_Raw())
    assert hasattr(client.takeout.messages, "export")
