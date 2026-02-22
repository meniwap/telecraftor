from __future__ import annotations

import asyncio

from bot_plugins.shared import ctx_from_router, peer_ref, require_admin
from telecraft.bot import (
    CallbackQueryEvent,
    MessageEvent,
    Router,
    and_,
    callback_data_startswith,
    command,
    incoming,
)
from telecraft.client.keyboards import InlineKeyboard


def _menu_markup(*, read_only: bool) -> object:
    kb = InlineKeyboard()
    kb.button("עזרה", callback_data="gb:help").button("סטטוס", callback_data="gb:status").row()
    if read_only:
        kb.button("כבה dry-run", callback_data="gb:readonly:off")
    else:
        kb.button("הפעל dry-run", callback_data="gb:readonly:on")
    kb.button("תפריט", callback_data="gb:menu")
    return kb.build()


def _help_text() -> str:
    return (
        "פקודות זמינות:\n"
        "- /start, /help, /id, /settings\n"
        "- /warn, /warnings, /unwarn, /mute, /unmute, /restrict, /unrestrict\n"
        "- /ban, /unban, /readd, /kick\n"
        "- /poll, /quiz, /autopin, /schedule, /jobs\n"
        "- /top, /stats, /modlog\n"
        "הערה: /readd מחזיר דרך הצטרפות (לינק/הנחיה), המשתמש מצטרף לבד."
    )


def _status_text(*, peer_key: str | None, read_only: bool) -> str:
    return (
        "סטטוס בוט:\n"
        f"- peer: {peer_key or 'unknown'}\n"
        f"- read_only_mode: {read_only}\n"
    )


async def setup(router: Router) -> None:
    ctx = ctx_from_router(router)

    @router.on_message(and_(incoming(), command("start")), stop=True)
    async def _on_start(event: MessageEvent) -> None:
        key = ctx.event_peer_key(event)
        read_only = ctx.get_peer_read_only(key)
        await event.reply(
            "שלום! זה Group Bot על MTProto.\n"
            "כאן אפשר לפתוח תפריט ולעבוד עם מודרציה/סטטיסטיקות.",
            reply_markup=_menu_markup(read_only=read_only),
        )

    @router.on_message(and_(incoming(), command("help")), stop=True)
    async def _on_help(event: MessageEvent) -> None:
        key = ctx.event_peer_key(event)
        await event.reply(
            _help_text(),
            reply_markup=_menu_markup(read_only=ctx.get_peer_read_only(key)),
        )

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
            "- שימוש בכפתורים למטה\n"
            "- או הקלד `readonly on` / `readonly off` תוך 45 שניות",
            reply_markup=_menu_markup(read_only=read_only),
        )
        try:
            answer = await router.ask(
                event,
                "אשף הגדרות: שלח `readonly on` או `readonly off`",
                timeout=45.0,
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

    @router.on_callback_query(callback_data_startswith("gb:"), stop=True)
    async def _on_callback(event: CallbackQueryEvent) -> None:
        data = (event.data_text or "").strip().lower()
        key = ctx.peer_key(event.peer_type, event.peer_id)
        read_only = ctx.get_peer_read_only(key)

        if data == "gb:help":
            await event.answer(message="פותח עזרה", alert=False)
            ref = peer_ref(event.peer_type, event.peer_id)
            if ref is not None:
                await ctx.app.messages.send(
                    ref,
                    _help_text(),
                    reply_to_msg_id=event.msg_id,
                    timeout=ctx.timeout,
                )
            return

        if data == "gb:status":
            await event.answer(message="סטטוס", alert=False)
            ref = peer_ref(event.peer_type, event.peer_id)
            if ref is not None:
                await ctx.app.messages.send(
                    ref,
                    _status_text(peer_key=key, read_only=read_only),
                    reply_to_msg_id=event.msg_id,
                    timeout=ctx.timeout,
                )
            return

        if data in {"gb:readonly:on", "gb:readonly:off"}:
            allowed = await ctx.is_admin(
                peer_type=event.peer_type,
                peer_id=event.peer_id,
                user_id=event.user_id,
            )
            if not allowed:
                await event.answer(message="אין הרשאה", alert=True)
                return
            if key is None:
                await event.answer(message="peer לא מזוהה", alert=True)
                return
            target_value = data.endswith(":on")
            ctx.set_peer_read_only(key, target_value)
            await event.answer(message="עודכן", alert=False)
            ref = peer_ref(event.peer_type, event.peer_id)
            if ref is not None and event.msg_id is not None:
                try:
                    await ctx.app.messages.edit(
                        ref,
                        int(event.msg_id),
                        _status_text(peer_key=key, read_only=target_value),
                        timeout=ctx.timeout,
                    )
                except Exception:
                    await ctx.app.messages.send(
                        ref,
                        _status_text(peer_key=key, read_only=target_value),
                        timeout=ctx.timeout,
                    )
            return

        if data == "gb:menu":
            await event.answer(message="תפריט", alert=False)
            ref = peer_ref(event.peer_type, event.peer_id)
            if ref is not None:
                await ctx.app.messages.send(
                    ref,
                    "תפריט ראשי",
                    reply_markup=_menu_markup(read_only=read_only),
                    timeout=ctx.timeout,
                )
            return

        await event.answer(message="לא זוהה", alert=False)


async def teardown(router: Router) -> None:
    _ = router
