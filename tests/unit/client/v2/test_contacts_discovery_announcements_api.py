from __future__ import annotations

import pytest

from telecraft.client import Client


class _Raw:
    pass


@pytest.mark.unit
def test_contacts_discovery_announcements_api__subclients__available() -> None:
    client = Client(raw=_Raw())
    assert hasattr(client.contacts, "requirements")
    assert hasattr(client.discovery, "sponsored")
