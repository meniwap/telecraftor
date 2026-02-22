from __future__ import annotations

from datetime import datetime, timezone

from bot_plugins.shared import decode_text, parse_target_and_rest, require_admin, resolve_user_ref
from telecraft.bot import MessageEvent, Router, and_, command, incoming


def _fmt_ts(ts: int) -> str:
    if ts <= 0:
        return "-"
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")


async def setup(router: Router) -> None:
    from bot_plugins.shared import ctx_from_router

    ctx = ctx_from_router(router)
    if not ctx.config.enable_stats:
        return

    @router.on_message(incoming(), stop=False)
    async def _collect_stats(event: MessageEvent) -> None:
        if event.sender_id is None:
            return
        key = ctx.event_peer_key(event)
        if key is None:
            return
        ctx.storage.increment_message_count(
            peer_key=key,
            user_id=int(event.sender_id),
        )

    @router.on_message(and_(incoming(), command("top")), stop=True)
    async def _on_top(event: MessageEvent) -> None:
        key = ctx.event_peer_key(event)
        if key is None:
            await event.reply("peer לא מזוהה.")
            return
        raw_limit = (event.command_args or "").strip()
        limit = 10
        if raw_limit:
            try:
                limit = max(1, min(50, int(raw_limit)))
            except ValueError:
                limit = 10
        rows = ctx.storage.list_top_users(peer_key=key, limit=limit)
        if not rows:
            await event.reply("אין נתונים עדיין.")
            return
        lines = [f"Top {limit} users:"]
        for idx, (user_id, message_count) in enumerate(rows, start=1):
            lines.append(f"{idx}. user:{user_id} -> {message_count}")
        await event.reply("\n".join(lines))

    @router.on_message(and_(incoming(), command("stats")), stop=True)
    async def _on_stats(event: MessageEvent) -> None:
        key = ctx.event_peer_key(event)
        if key is None:
            await event.reply("peer לא מזוהה.")
            return
        args = (event.command_args or "").strip()
        target_user_id: int | None = event.sender_id
        target_ref = f"user:{target_user_id}" if target_user_id is not None else "unknown"
        if args:
            target_token, _ = parse_target_and_rest(args)
            try:
                target_user_id, target_ref = await resolve_user_ref(ctx, target_token)
            except Exception as ex:  # noqa: BLE001
                await event.reply(f"לא הצלחתי לפתור משתמש יעד: {decode_text(ex)}")
                return
        if target_user_id is None:
            await event.reply("לא הצלחתי לזהות משתמש.")
            return
        stats = ctx.storage.get_user_stats(peer_key=key, user_id=int(target_user_id))
        warns = ctx.storage.get_warning_count(peer_key=key, user_id=int(target_user_id))
        await event.reply(
            "סטטיסטיקה:\n"
            f"- user: {target_ref}\n"
            f"- message_count: {stats['message_count']}\n"
            f"- warnings: {warns}\n"
            f"- last_seen_utc: {_fmt_ts(stats['last_seen_ts'])}"
        )

    @router.on_message(and_(incoming(), command("modlog")), stop=True)
    async def _on_modlog(event: MessageEvent) -> None:
        if not await require_admin(ctx=ctx, event=event, action_name="modlog"):
            return
        key = ctx.event_peer_key(event)
        if key is None:
            await event.reply("peer לא מזוהה.")
            return
        raw_limit = (event.command_args or "").strip()
        limit = 10
        if raw_limit:
            try:
                limit = max(1, min(30, int(raw_limit)))
            except ValueError:
                limit = 10
        rows = ctx.storage.list_mod_log(peer_key=key, limit=limit)
        if not rows:
            await event.reply("modlog ריק.")
            return
        lines = ["modlog:"]
        for row in rows:
            lines.append(
                f"- {_fmt_ts(int(row['ts']))} {row['action']} "
                f"actor={row['actor_id']} target={row['target_user_id']} "
                f"details={row['details']}"
            )
        await event.reply("\n".join(lines))


async def teardown(router: Router) -> None:
    _ = router
