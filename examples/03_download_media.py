from __future__ import annotations

import argparse
import asyncio

from _common import build_client


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download the newest media from a peer.")
    parser.add_argument("peer", help="@username, user:ID, chat:ID, or channel:ID")
    parser.add_argument("--dest", default="downloads/", help="Output directory")
    parser.add_argument("--limit", type=int, default=25, help="Messages to scan")
    return parser.parse_args()


async def main() -> None:
    args = _parse_args()
    client = build_client()
    await client.connect()
    try:
        async for message in client.messages.iter_messages(args.peer, limit=args.limit):
            saved_path = await client.media.download(message, dest=args.dest)
            if saved_path:
                print(saved_path)
                return
        raise SystemExit("No downloadable media found in the scanned messages.")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
