"""
Who am I — connect with the saved session and print the logged-in account.

This is the quickest way to verify that your session works.

Run:
    python examples/02_whoami.py
"""

from __future__ import annotations

import asyncio

from _common import build_client


def _s(value: object) -> str:
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", errors="replace")
    return str(value) if value else ""


async def main() -> None:
    client = build_client()
    await client.connect()
    try:
        full = await client.users.full("self")
        users = getattr(full, "users", None) or []
        me = users[0] if users else full
        first = _s(getattr(me, "first_name", ""))
        last = _s(getattr(me, "last_name", ""))
        name = " ".join(p for p in (first, last) if p)
        username = _s(getattr(me, "username", ""))
        print(f"Logged in as: {name}" + (f" (@{username})" if username else ""))
        print(f"User id: {getattr(me, 'id', '?')}")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
