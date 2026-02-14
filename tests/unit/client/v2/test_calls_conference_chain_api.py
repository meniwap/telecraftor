from __future__ import annotations

import pytest

from telecraft.client import Client


class _Raw:
    pass


@pytest.mark.unit
def test_calls_conference_chain_api__subclients__available() -> None:
    client = Client(raw=_Raw())
    assert hasattr(client.calls.group, "chain")
    assert hasattr(client.calls.group.chain, "blocks")
    assert hasattr(client.calls.conference, "delete_participants")
    assert hasattr(client.calls.conference, "broadcast")
    assert hasattr(client.calls.conference, "invite")
    assert hasattr(client.calls.conference, "decline_invite")
