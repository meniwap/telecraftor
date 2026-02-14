from __future__ import annotations

import pytest

from telecraft.client import Client


class _Raw:
    pass


@pytest.mark.unit
def test_account_identity__subclients__available() -> None:
    client = Client(raw=_Raw())
    assert hasattr(client.account, "identity")
    assert hasattr(client.account.identity, "check_username")
    assert hasattr(client.account, "personal_channel")
