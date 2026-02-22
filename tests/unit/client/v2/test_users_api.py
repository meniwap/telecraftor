from __future__ import annotations

from telecraft.client import Client


class _Raw:
    is_connected = False


def test_users__namespace__returns_expected_shape() -> None:
    client = Client(raw=_Raw())
    assert hasattr(client, "users")


def test_users__full__returns_expected_shape() -> None:
    client = Client(raw=_Raw())
    assert hasattr(client.users, "full")
