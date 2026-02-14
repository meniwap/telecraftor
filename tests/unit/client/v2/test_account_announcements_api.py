from __future__ import annotations

import pytest

from telecraft.client import Client


class _Raw:
    pass


@pytest.mark.unit
def test_account_announcements_api__subclients__available() -> None:
    client = Client(raw=_Raw())
    assert hasattr(client.account, "profile_tab")
    assert hasattr(client.account, "gift_themes")
    assert hasattr(client.account, "music")
    assert hasattr(client.account.music, "saved")
    assert hasattr(client.account, "paid_messages")
    assert hasattr(client.account, "passkeys")
