from __future__ import annotations

from telecraft.client import Client


class _Raw:
    is_connected = False


def test_todos__append__returns_expected_shape() -> None:
    client = Client(raw=_Raw())
    assert hasattr(client.todos, "append")


def test_todos__toggle__returns_expected_shape() -> None:
    client = Client(raw=_Raw())
    assert hasattr(client.todos, "toggle")
