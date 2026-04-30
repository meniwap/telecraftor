from __future__ import annotations

import asyncio

from _common import build_client

from telecraft.bot import Dispatcher, MessageEvent, Router, text


async def main() -> None:
    app = build_client()
    await app.connect()
    router = Router()

    @router.on_message(text())
    async def echo(event: MessageEvent) -> None:
        if event.text and not event.text.startswith("echo: "):
            await event.reply("echo: " + event.text)

    dispatcher = Dispatcher(
        client=app.raw,
        router=router,
        ignore_outgoing=True,
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
