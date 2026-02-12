from __future__ import annotations

from telecraft.client import Client


class _Raw:
    is_connected = False


def test_calls_group__create__returns_expected_shape() -> None:
    client = Client(raw=_Raw())
    assert hasattr(client.calls.group, "create")


def test_calls_stream__rtmp_url__returns_expected_shape() -> None:
    client = Client(raw=_Raw())
    assert hasattr(client.calls.stream, "rtmp_url")
