"""
Scheduled reminders — combine the bot Router with the built-in Scheduler.

/remind <seconds> <text>  schedules a one-off reminder in the same chat.
The scheduler also keeps a recurring job running (a console heartbeat).

Run:
    python examples/07_scheduled_reminders.py

Self-test from your own account (type into Saved Messages):
    TELECRAFT_ALLOW_OUTGOING=1 python examples/07_scheduled_reminders.py
    /remind 5 drink water

Stop with Ctrl+C.
"""

from __future__ import annotations

import asyncio

from _common import allow_outgoing, build_client

from telecraft.bot import Dispatcher, MessageEvent, Router, Scheduler, command


async def main() -> None:
    app = build_client()
    await app.connect()
    print("Reminder bot is running. Try: /remind 5 drink water. Ctrl+C to stop.")

    router = Router()
    scheduler = Scheduler()

    # A recurring job: prints a heartbeat so you can see the scheduler ticking.
    scheduler.every(60.0, lambda: print("[scheduler] still alive"), name="heartbeat")

    @router.on_message(command("remind"))
    async def remind(event: MessageEvent) -> None:
        parts = (event.command_args or "").split(maxsplit=1)
        if not parts:
            await event.reply("Usage: /remind <seconds> <text>")
            return
        try:
            seconds = float(parts[0])
        except ValueError:
            await event.reply("Usage: /remind <seconds> <text>")
            return
        text = parts[1] if len(parts) > 1 else "Reminder!"
        scheduler.call_later(seconds, lambda: event.reply(f"⏰ {text}"))
        await event.reply(f"Got it - reminding you in {seconds:.0f}s.")

    dispatcher = Dispatcher(
        client=app.raw,
        router=router,
        ignore_outgoing=not allow_outgoing(),
        ignore_before_start=True,
    )
    try:
        await dispatcher.run()
    finally:
        await scheduler.stop()
        await app.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
