from __future__ import annotations

from telecraft.client import Client


class _Raw:
    is_connected = False


def test_auth__namespace__returns_expected_shape() -> None:
    client = Client(raw=_Raw())
    assert hasattr(client, "auth")


def test_auth__send_code__returns_expected_shape() -> None:
    client = Client(raw=_Raw())
    assert hasattr(client.auth, "send_code")
