from __future__ import annotations

from telecraft.client import Client


class _Raw:
    is_connected = False


def test_stats_channels__broadcast__returns_expected_shape() -> None:
    client = Client(raw=_Raw())
    assert hasattr(client.stats.channels, "broadcast")


def test_stats_graph__fetch__returns_expected_shape() -> None:
    client = Client(raw=_Raw())
    assert hasattr(client.stats.graph, "fetch")
