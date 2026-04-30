from __future__ import annotations

import argparse
import asyncio

from _common import build_client


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send a text message with Telecraft MTProto.")
    parser.add_argument("peer", help="@username, phone, user:ID, chat:ID, or channel:ID")
    parser.add_argument("text", help="Message text")
    return parser.parse_args()


async def main() -> None:
    args = _parse_args()
    client = build_client()
    await client.connect()
    try:
        sent = await client.messages.send(args.peer, args.text)
        print(sent)
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
