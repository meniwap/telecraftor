from __future__ import annotations

from telecraft.client import Client


class _Raw:
    is_connected = False


def test_reports__peer__returns_expected_shape() -> None:
    client = Client(raw=_Raw())
    assert hasattr(client.reports, "peer")


def test_reports__spam__returns_expected_shape() -> None:
    client = Client(raw=_Raw())
    assert hasattr(client.reports, "spam")
