from __future__ import annotations

import pytest

from telecraft.client import Client


class _Raw:
    pass


@pytest.mark.unit
def test_payments_api__subclients__available() -> None:
    client = Client(raw=_Raw())
    assert hasattr(client, "payments")
    assert hasattr(client.payments, "forms")
    assert hasattr(client.payments, "invoice")
    assert hasattr(client.payments, "gift_codes")
    assert hasattr(client.payments, "stars")
