"""
Echo bot — the classic first bot: reply "echo: <text>" to every text message.

Run:
    python examples/01_echo_bot.py

Then ask someone to DM you (the bot runs on your user session), or self-test
from a single account:
    TELECRAFT_ALLOW_OUTGOING=1 python examples/01_echo_bot.py
    ...and send any message to your Saved Messages.

Stop with Ctrl+C.
"""

from __future__ import annotations

import asyncio

from _common import allow_outgoing, build_client

from telecraft.bot import Dispatcher, MessageEvent, Router, text


async def main() -> None:
    app = build_client()
    await app.connect()
    print("Echo bot is running. Send a message; Ctrl+C to stop.")

    router = Router()

    @router.on_message(text())
    async def echo(event: MessageEvent) -> None:
        # Skip our own echoes so the bot never replies to itself in a loop.
        if event.text is None or event.text.startswith("echo: "):
            return
        await event.reply("echo: " + event.text)

    dispatcher = Dispatcher(
        client=app.raw,
        router=router,
        ignore_outgoing=not allow_outgoing(),
        ignore_before_start=True,
    )
    try:
        await dispatcher.run()
    finally:
        await app.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
