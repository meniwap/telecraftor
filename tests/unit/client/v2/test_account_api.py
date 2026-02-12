from __future__ import annotations

from telecraft.client import Client


class _Raw:
    is_connected = False


def test_account_sessions__list__returns_expected_shape() -> None:
    client = Client(raw=_Raw())
    assert hasattr(client.account.sessions, "list")


def test_account_wallpapers__list__returns_expected_shape() -> None:
    client = Client(raw=_Raw())
    assert hasattr(client.account.wallpapers, "list")
