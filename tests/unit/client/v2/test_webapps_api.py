from __future__ import annotations

from telecraft.client import Client


class _Raw:
    is_connected = False


def test_webapps__request__returns_expected_shape() -> None:
    client = Client(raw=_Raw())
    assert hasattr(client.webapps, "request")


def test_webapps__invoke_custom__returns_expected_shape() -> None:
    client = Client(raw=_Raw())
    assert hasattr(client.webapps, "invoke_custom")
