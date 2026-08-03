from __future__ import annotations

import asyncio

from telecraft.client import Client


class _Raw:
    is_connected = False


def test_auth__namespace__returns_expected_shape() -> None:
    client = Client(raw=_Raw())
    assert hasattr(client, "auth")


def test_auth__send_code__returns_expected_shape() -> None:
    client = Client(raw=_Raw())
    assert hasattr(client.auth, "send_code")


def test_auth__log_out__uses_local_cleanup_aware_client_method() -> None:
    class Raw:
        is_connected = True

        def __init__(self) -> None:
            self.timeouts: list[float] = []

        async def log_out(self, *, timeout: float) -> object:
            self.timeouts.append(timeout)
            return {"ok": True}

    raw = Raw()
    client = Client(raw=raw)  # type: ignore[arg-type]

    assert asyncio.run(client.auth.log_out(timeout=7.0)) == {"ok": True}
    assert raw.timeouts == [7.0]
