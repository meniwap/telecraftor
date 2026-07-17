from __future__ import annotations

import asyncio

from bot_plugins.shared import ctx_from_router, require_admin
from telecraft.bot import MessageEvent, Router, and_, command, incoming


def _help_text() -> str:
    return (
        "פקודות זמינות:\n"
        "- /start, /help, /id, /settings\n"
        "- /warn, /warnings, /unwarn, /mute, /unmute, /restrict, /unrestrict\n"
        "- /ban, /unban, /readd, /kick\n"
        "- /poll, /quiz, /autopin, /schedule, /unschedule, /jobs\n"
        "- /top, /stats, /modlog\n"
        "הערה: /readd מחזיר דרך הצטרפות (לינק/הנחיה), המשתמש מצטרף לבד."
    )


async def setup(router: Router) -> None:
    ctx = ctx_from_router(router)

    @router.on_message(and_(incoming(), command("start")), stop=True)
    async def _on_start(event: MessageEvent) -> None:
        await event.reply(
            "שלום! זה Group Bot על MTProto.\nשלח /help לרשימת פקודות או /settings להגדרות dry-run.",
        )

    @router.on_message(and_(incoming(), command("help")), stop=True)
    async def _on_help(event: MessageEvent) -> None:
        await event.reply(_help_text())

    @router.on_message(and_(incoming(), command("id")), stop=True)
    async def _on_id(event: MessageEvent) -> None:
        await event.reply(
            "IDs:\n"
            f"- peer: {event.peer_type}:{event.peer_id}\n"
            f"- sender_id: {event.sender_id}\n"
            f"- msg_id: {event.msg_id}"
        )

    @router.on_message(and_(incoming(), command("settings")), stop=True)
    async def _on_settings(event: MessageEvent) -> None:
        if not await require_admin(ctx=ctx, event=event, action_name="settings"):
            return
        key = ctx.event_peer_key(event)
        read_only = ctx.get_peer_read_only(key)
        await event.reply(
            "הגדרות מהירות:\n"
            f"- מצב נוכחי: read_only_mode={read_only}\n"
            "- הקלד `readonly on` / `readonly off` תוך 45 שניות",
        )
        try:
            answer = await router.ask(
                event,
                "אשף הגדרות: שלח `readonly on` או `readonly off`",
                timeout=45.0,
                same_sender=True,
            )
        except asyncio.TimeoutError:
            await event.reply("פג הזמן של אשף ההגדרות.")
            return

        text = (answer.text or "").strip().lower()
        if text == "readonly on" and key is not None:
            ctx.set_peer_read_only(key, True)
            await answer.reply("dry-run הופעל לקבוצה הזו.")
            return
        if text == "readonly off" and key is not None:
            ctx.set_peer_read_only(key, False)
            await answer.reply("dry-run כובה לקבוצה הזו.")
            return
        await answer.reply("קלט לא מזוהה. נסה שוב עם /settings.")


async def teardown(router: Router) -> None:
    _ = router
