"""
Command bot — /ping, /id and /help, with automatic reconnect.

Shows the `command()` filter plus `run_userbot`, which reconnects with
exponential backoff if the connection drops — a long-running bot in ~40 lines.

Run:
    python examples/04_command_bot.py

Self-test from your own account (commands typed into Saved Messages):
    TELECRAFT_ALLOW_OUTGOING=1 python examples/04_command_bot.py

Stop with Ctrl+C.
"""

from __future__ import annotations

import asyncio

from _common import allow_outgoing, build_client

from telecraft.bot import (
    Dispatcher,
    MessageEvent,
    ReconnectPolicy,
    Router,
    command,
    run_userbot,
)

HELP_TEXT = (
    "Available commands:\n"
    "/ping - check that the bot is alive\n"
    "/id - show ids for this chat\n"
    "/help - this message"
)


def build_router() -> Router:
    router = Router()

    @router.on_message(command("ping"))
    async def ping(event: MessageEvent) -> None:
        await event.reply("pong")

    @router.on_message(command("id"))
    async def ids(event: MessageEvent) -> None:
        await event.reply(
            f"peer: {event.peer_type}:{event.peer_id}\n"
            f"from user: {event.user_id}\n"
            f"message id: {event.msg_id}"
        )

    @router.on_message(command("help"))
    async def help_cmd(event: MessageEvent) -> None:
        await event.reply(HELP_TEXT)

    return router


async def main() -> None:
    app = build_client()
    print("Command bot is running. Try /ping, /id, /help. Ctrl+C to stop.")

    def make_dispatcher(client: object, router: Router) -> Dispatcher:
        return Dispatcher(
            client=client,
            router=router,
            ignore_outgoing=not allow_outgoing(),
            ignore_before_start=True,
        )

    await run_userbot(
        client=app.raw,
        router=build_router(),
        make_dispatcher=make_dispatcher,
        reconnect=ReconnectPolicy(initial_delay_seconds=1.0, max_delay_seconds=30.0),
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
