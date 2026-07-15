"""
Download media — scan a peer's recent messages and save the newest attachment.

Run:
    python examples/05_download_media.py                 # scan Saved Messages
    python examples/05_download_media.py @channel
    python examples/05_download_media.py @friend --dest downloads/ --limit 50
"""

from __future__ import annotations

import argparse
import asyncio

from _common import build_client


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download the newest media from a peer.")
    parser.add_argument(
        "peer",
        nargs="?",
        default="self",
        help='@username, "self", user:ID, chat:ID, or channel:ID',
    )
    parser.add_argument("--dest", default="downloads/", help="Output directory")
    parser.add_argument("--limit", type=int, default=25, help="Messages to scan")
    return parser.parse_args()


async def main() -> None:
    args = _parse_args()
    client = build_client()
    await client.connect()
    try:
        peer: object = args.peer
        if args.peer.strip().lower() == "self":
            # Saved Messages = a chat with your own user id.
            full = await client.users.full("self")
            peer = ("user", int(full.users[0].id))
        async for message in client.messages.iter_messages(peer, limit=args.limit):
            saved_path = await client.media.download(message, dest=args.dest)
            if saved_path:
                print(f"Saved: {saved_path}")
                return
        raise SystemExit("No downloadable media found in the scanned messages.")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
