"""
Conversation form — a multi-step dialog using the Router's built-in
conversation support (`router.ask` waits for the next reply in the same chat).
The form also restricts answers to the user who started it.

Send /form to the account running this bot, answer the two questions,
and get a summary back.

Run:
    python examples/06_conversation_form.py

Self-test from your own account (type /form into Saved Messages):
    TELECRAFT_ALLOW_OUTGOING=1 python examples/06_conversation_form.py

Stop with Ctrl+C.
"""

from __future__ import annotations

import asyncio

from _common import allow_outgoing, build_client

from telecraft.bot import Dispatcher, MessageEvent, Router, command

PROMPT = "❓"  # question prompts start with this marker
DONE = "✅"


def _is_answer(event: MessageEvent) -> bool:
    # Accept plain text only; skip the bot's own prompts so a self-test in
    # Saved Messages doesn't answer questions with the questions themselves.
    return bool(event.text) and not event.text.startswith((PROMPT, DONE, "/"))


async def main() -> None:
    app = build_client()
    await app.connect()
    print("Form bot is running. Send /form to start. Ctrl+C to stop.")

    router = Router()

    async def run_form(event: MessageEvent) -> None:
        try:
            ask = router.ask
            name = await ask(
                event,
                f"{PROMPT} What's your name?",
                filt=_is_answer,
                timeout=120,
                same_sender=True,
            )
            city = await ask(
                event,
                f"{PROMPT} Which city?",
                filt=_is_answer,
                timeout=120,
                same_sender=True,
            )
        except (TimeoutError, asyncio.TimeoutError):  # asyncio alias needed on Python 3.10
            await event.reply("Form timed out. Send /form to try again.")
            return
        await event.reply(f"{DONE} Nice to meet you, {name.text} from {city.text}!")

    @router.on_message(command("form"))
    async def form(event: MessageEvent) -> None:
        # Dispatcher keeps receiving conversation answers while this handler
        # waits, and preserves order for this sender within this peer.
        await run_form(event)

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
