"""
Send a message — one call, any peer.

Run:
    python examples/03_send_message.py                       # to Saved Messages
    python examples/03_send_message.py @friend "hi there"
    python examples/03_send_message.py user:12345 "hello"

Peers can be @username, phone, "self"/"me", user:ID, chat:ID, or channel:ID.
"""

from __future__ import annotations

import argparse
import asyncio

from _common import build_client


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send a text message with Telecraft.")
    parser.add_argument(
        "peer",
        nargs="?",
        default="self",
        help='@username, phone, "self"/"me", user:ID, chat:ID, or channel:ID',
    )
    parser.add_argument("text", nargs="?", default="Hello from Telecraft!", help="Message text")
    return parser.parse_args()


async def main() -> None:
    args = _parse_args()
    client = build_client()
    await client.connect()
    try:
        await client.messages.send(args.peer, args.text)
        print(f"Sent to {args.peer}: {args.text}")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
