from __future__ import annotations

from telecraft.client import Client


class _Raw:
    is_connected = False


def test_uploads__namespace__returns_expected_shape() -> None:
    client = Client(raw=_Raw())
    assert hasattr(client, "uploads")


def test_uploads__upload_file__returns_expected_shape() -> None:
    client = Client(raw=_Raw())
    assert hasattr(client.uploads, "upload_file")
