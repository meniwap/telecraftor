from __future__ import annotations

from telecraft.client import Client


class _Raw:
    is_connected = False


def test_langpack__namespace__returns_expected_shape() -> None:
    client = Client(raw=_Raw())
    assert hasattr(client, "langpack")


def test_langpack__languages__returns_expected_shape() -> None:
    client = Client(raw=_Raw())
    assert hasattr(client.langpack, "languages")
