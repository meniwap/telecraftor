from __future__ import annotations

from telecraft.client import Client


class _Raw:
    is_connected = False


def test_discovery_channels__recommended__returns_expected_shape() -> None:
    client = Client(raw=_Raw())
    assert hasattr(client.discovery.channels, "recommended")


def test_discovery__peer_settings__returns_expected_shape() -> None:
    client = Client(raw=_Raw())
    assert hasattr(client.discovery, "peer_settings")
