from __future__ import annotations

import argparse
import asyncio

from _common import build_client

from telecraft.client.keyboards import InlineKeyboard


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send an MTProto bot inline keyboard.")
    parser.add_argument("peer", help="@username, user:ID, chat:ID, or channel:ID")
    return parser.parse_args()


async def main() -> None:
    args = _parse_args()
    keyboard = InlineKeyboard()
    keyboard.button("Yes", callback_data="demo_yes").button("No", callback_data="demo_no")

    client = build_client()
    await client.connect()
    try:
        await client.messages.send(args.peer, "Choose an option:", reply_markup=keyboard.build())
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
