from __future__ import annotations

import time

from bot_plugins.shared import dry_run_guard, parse_target_and_rest, peer_ref, require_admin
from telecraft.bot import MessageEvent, Router, and_, command, incoming


def _parse_poll_args(raw: str) -> tuple[str, list[str]]:
    parts = [part.strip() for part in raw.split("|") if part.strip()]
    if len(parts) < 3:
        raise ValueError("usage")
    return parts[0], parts[1:]


def _parse_quiz_args(raw: str) -> tuple[str, list[str], int]:
    parts = [part.strip() for part in raw.split("|") if part.strip()]
    if len(parts) < 4:
        raise ValueError("usage")
    question = parts[0]
    options = parts[1:-1]
    if len(options) < 2:
        raise ValueError("usage")
    try:
        correct_1based = int(parts[-1])
    except ValueError as ex:
        raise ValueError("usage") from ex
    correct_index = correct_1based - 1
    if correct_index < 0 or correct_index >= len(options):
        raise ValueError("usage")
    return question, options, correct_index


async def setup(router: Router) -> None:
    from bot_plugins.shared import ctx_from_router

    ctx = ctx_from_router(router)
    if not ctx.config.enable_utilities:
        return

    @router.on_message(and_(incoming(), command("autopin")), stop=True)
    async def _on_autopin(event: MessageEvent) -> None:
        if not await require_admin(ctx=ctx, event=event, action_name="autopin"):
            return
        ref = peer_ref(event.peer_type, event.peer_id)
        if ref is None:
            await event.reply("peer לא מזוהה.")
            return
        if event.reply_to_msg_id is None:
            await event.reply("שימוש: /autopin בתגובה להודעה שתרצה להצמיד.")
            return
        details = f"{ref} msg_id={event.reply_to_msg_id}"
        if await dry_run_guard(ctx=ctx, event=event, action="autopin", details=details):
            return
        await ctx.app.messages.pin(ref, int(event.reply_to_msg_id), timeout=ctx.timeout)
        await event.reply("ההודעה הוצמדה.")

    @router.on_message(and_(incoming(), command("poll")), stop=True)
    async def _on_poll(event: MessageEvent) -> None:
        if not await require_admin(ctx=ctx, event=event, action_name="poll"):
            return
        ref = peer_ref(event.peer_type, event.peer_id)
        if ref is None:
            await event.reply("peer לא מזוהה.")
            return
        try:
            question, options = _parse_poll_args(event.command_args or "")
        except ValueError:
            await event.reply("שימוש: /poll שאלה | אופציה1 | אופציה2 [| אופציה3 ...]")
            return
        await ctx.app.polls.send(
            ref,
            question=question,
            options=options,
            public_voters=False,
            timeout=ctx.timeout,
        )
        await event.reply("הסקר נשלח.")

    @router.on_message(and_(incoming(), command("quiz")), stop=True)
    async def _on_quiz(event: MessageEvent) -> None:
        if not await require_admin(ctx=ctx, event=event, action_name="quiz"):
            return
        ref = peer_ref(event.peer_type, event.peer_id)
        if ref is None:
            await event.reply("peer לא מזוהה.")
            return
        try:
            question, options, correct_index = _parse_quiz_args(event.command_args or "")
        except ValueError:
            await event.reply("שימוש: /quiz שאלה | אופציה1 | אופציה2 | אינדקס-נכון(1-based)")
            return
        await ctx.app.polls.send_quiz(
            ref,
            question=question,
            options=options,
            correct_option=correct_index,
            timeout=ctx.timeout,
        )
        await event.reply("החידון נשלח.")

    @router.on_message(and_(incoming(), command("schedule")), stop=True)
    async def _on_schedule(event: MessageEvent) -> None:
        if not await require_admin(ctx=ctx, event=event, action_name="schedule"):
            return
        ref = peer_ref(event.peer_type, event.peer_id)
        if ref is None:
            await event.reply("peer לא מזוהה.")
            return
        raw = (event.command_args or "").strip()
        first, text = parse_target_and_rest(raw)
        if not first or not text:
            await event.reply("שימוש: /schedule <seconds> <text>")
            return
        try:
            interval = int(first)
        except ValueError:
            await event.reply("seconds חייב להיות מספר.")
            return
        if interval <= 0:
            await event.reply("seconds חייב להיות גדול מ-0.")
            return
        name = f"manual-{int(time.time())}-{event.sender_id or 0}"
        details = f"name={name} every={interval}s peer={ref}"
        if await dry_run_guard(ctx=ctx, event=event, action="schedule", details=details):
            return
        await ctx.register_or_update_schedule(
            name=name,
            text=text,
            interval_seconds=interval,
            peer_ref=ref,
            enabled=True,
        )
        await event.reply(f"נוספה משימה `{name}` כל {interval} שניות.")

    @router.on_message(and_(incoming(), command("jobs")), stop=True)
    async def _on_jobs(event: MessageEvent) -> None:
        if not await require_admin(ctx=ctx, event=event, action_name="jobs"):
            return
        jobs = ctx.storage.list_scheduled_jobs(enabled_only=False)
        if not jobs:
            await event.reply("אין משימות מתוזמנות.")
            return
        lines = ["משימות מתוזמנות:"]
        for job in jobs[:20]:
            lines.append(
                f"- {job.name}: every={job.interval_seconds}s "
                f"enabled={job.enabled} peer={job.peer_ref}"
            )
        await event.reply("\n".join(lines))


async def teardown(router: Router) -> None:
    _ = router
