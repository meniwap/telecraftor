from __future__ import annotations

import pytest

from telecraft.client import Client


class _Raw:
    pass


@pytest.mark.unit
def test_premium_api__subclients__available() -> None:
    client = Client(raw=_Raw())
    assert hasattr(client, "premium")
    assert hasattr(client.premium, "boosts")
    assert hasattr(client.premium.boosts, "list")
    assert hasattr(client.premium.boosts, "my")
    assert hasattr(client.premium.boosts, "apply")
    assert hasattr(client.premium.boosts, "status")
    assert hasattr(client.premium.boosts, "user")
