from __future__ import annotations

import asyncio

from _common import build_client


async def main() -> None:
    client = build_client()
    await client.connect()
    try:
        me = await client.users.full("self")
        print(me)
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
