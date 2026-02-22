from __future__ import annotations

import time
from typing import Any

from bot_plugins.shared import (
    decode_text,
    dry_run_guard,
    has_blocked_keyword,
    has_link,
    normalize_restrict_profile,
    now_ts,
    parse_minutes_target,
    parse_restrict_args,
    parse_target_and_rest,
    peer_ref,
    require_admin,
    resolve_user_ref,
)
from telecraft.bot import MessageEvent, Router, and_, command, incoming
from telecraft.client import make_banned_rights


def _is_channel_event(event: MessageEvent) -> bool:
    return event.peer_type == "channel" and event.peer_id is not None


def _public_join_link_for_event(
    *,
    app: Any,
    peer_type: str | None,
    peer_id: int | None,
) -> str | None:
    if peer_type is None or peer_id is None:
        return None

    raw = getattr(app, "raw", None)
    entities = getattr(raw, "entities", None) if raw is not None else None
    username_map = getattr(entities, "username_to_peer", None) if entities is not None else None
    if isinstance(username_map, dict):
        for username, peer in username_map.items():
            if (
                isinstance(username, str)
                and isinstance(peer, tuple)
                and len(peer) == 2
                and str(peer[0]) == str(peer_type)
                and int(peer[1]) == int(peer_id)
            ):
                return f"https://t.me/{username}"
    return None


def build_restrict_rights(*, profile: str, until_date: int) -> object:
    normalized = normalize_restrict_profile(profile)
    if normalized == "all":
        return make_banned_rights(
            send_messages=True,
            send_media=True,
            send_stickers=True,
            send_gifs=True,
            send_games=True,
            send_inline=True,
            embed_links=True,
            send_polls=True,
            send_plain=True,
            send_photos=True,
            send_videos=True,
            send_roundvideos=True,
            send_audios=True,
            send_voices=True,
            send_docs=True,
            until_date=until_date,
        )
    if normalized == "media":
        return make_banned_rights(
            send_media=True,
            send_stickers=True,
            send_gifs=True,
            send_photos=True,
            send_videos=True,
            send_roundvideos=True,
            send_audios=True,
            send_voices=True,
            send_docs=True,
            until_date=until_date,
        )
    if normalized == "links":
        return make_banned_rights(embed_links=True, until_date=until_date)
    if normalized == "text":
        return make_banned_rights(send_plain=True, until_date=until_date)
    raise ValueError(f"unknown profile: {profile}")


async def try_readd_user(
    *,
    app: Any,
    channel_ref: str,
    target_ref: str,
    target_user_id: int,
    timeout: float,
) -> tuple[bool, str | None, str | None]:
    ttl_seconds = 1800
    expire_date = int(time.time()) + ttl_seconds

    def _extract_link(result: Any) -> str | None:
        candidates = [
            result,
            getattr(result, "invite", None),
            getattr(result, "new_invite", None),
        ]
        invites = getattr(result, "invites", None)
        if isinstance(invites, list):
            candidates.extend(invites)
        for item in candidates:
            if item is None:
                continue
            raw = getattr(item, "link", None)
            link = decode_text(raw).strip() if raw is not None else ""
            if link.startswith("http://") or link.startswith("https://"):
                return link
            if link.startswith("t.me/"):
                return "https://" + link
        return None

    try:
        res = await app.chats.invites.create(
            channel_ref,
            expire_date=expire_date,
            usage_limit=1,
            request_needed=False,
            title=f"readd-{int(target_user_id)}",
            timeout=timeout,
        )
    except Exception as ex:  # noqa: BLE001
        return False, None, decode_text(ex)
    link = _extract_link(res)
    if not link:
        return False, None, "invite link was not returned by Telegram"
    return True, link, None


async def setup(router: Router) -> None:
    from bot_plugins.shared import ctx_from_router

    ctx = ctx_from_router(router)
    if not ctx.config.enable_moderation:
        return

    async def _warn_user(
        *,
        event: MessageEvent,
        target_user_id: int,
        reason: str,
    ) -> int:
        key = ctx.event_peer_key(event)
        if key is None:
            return 0
        count = ctx.storage.increment_warning(
            peer_key=key,
            user_id=target_user_id,
            reason=reason,
            ts=now_ts(),
        )
        ctx.storage.add_mod_log(
            peer_key=key,
            action="warn",
            actor_id=event.sender_id,
            target_user_id=target_user_id,
            details={"reason": reason, "count": count},
            ts=now_ts(),
        )
        return count

    async def _maybe_auto_ban(
        *,
        event: MessageEvent,
        target_user_id: int,
        count: int,
        reason: str,
    ) -> None:
        key = ctx.event_peer_key(event)
        if key is None:
            return
        if count < ctx.config.warn_threshold:
            return
        if not _is_channel_event(event):
            return
        details = f"user:{target_user_id} reason={reason} warnings={count}"
        if await dry_run_guard(
            ctx=ctx,
            event=event,
            action="auto-ban",
            details=details,
        ):
            return
        channel_ref = peer_ref(event.peer_type, event.peer_id)
        if channel_ref is None:
            return
        target_ref = f"user:{target_user_id}"
        await ctx.app.admin.ban(channel_ref, target_ref, timeout=ctx.timeout)
        ctx.storage.add_mod_log(
            peer_key=key,
            action="auto_ban",
            actor_id=event.sender_id,
            target_user_id=target_user_id,
            details={"reason": reason, "warnings": count},
            ts=now_ts(),
        )
        await event.reply(f"המשתמש {target_ref} נחסם אוטומטית (warnings={count}).")

    async def _restrict_user(
        *,
        event: MessageEvent,
        target_ref: str,
        target_user_id: int,
        minutes: int,
        profile: str,
        action_name: str,
        response_mode: str,
    ) -> None:
        key = ctx.event_peer_key(event)
        if key is None:
            return
        if not _is_channel_event(event):
            await event.reply("פעולת restrict נתמכת כרגע רק בסופרגרופ/ערוץ (channel).")
            return
        channel_ref = peer_ref(event.peer_type, event.peer_id)
        if channel_ref is None:
            return
        normalized_profile = normalize_restrict_profile(profile)
        until_date = int(time.time()) + (minutes * 60)
        rights = build_restrict_rights(
            profile=normalized_profile,
            until_date=until_date,
        )
        details = f"{target_ref} profile={normalized_profile} for {minutes}m"
        if await dry_run_guard(ctx=ctx, event=event, action=action_name, details=details):
            return
        await ctx.app.admin.restrict(channel_ref, target_ref, rights=rights, timeout=ctx.timeout)
        ctx.storage.add_mod_log(
            peer_key=key,
            action=action_name,
            actor_id=event.sender_id,
            target_user_id=target_user_id,
            details={"minutes": minutes, "profile": normalized_profile},
            ts=now_ts(),
        )
        if response_mode == "mute":
            await event.reply(f"{target_ref} הושתק ל-{minutes} דקות.")
            return
        await event.reply(
            f"{target_ref} הוגבל בפרופיל `{normalized_profile}` ל-{minutes} דקות."
        )

    async def _unrestrict_user(
        *,
        event: MessageEvent,
        target_ref: str,
        target_user_id: int,
        action_name: str,
        response_mode: str,
    ) -> None:
        key = ctx.event_peer_key(event)
        if key is None:
            return
        if not _is_channel_event(event):
            await event.reply("פעולת unrestrict נתמכת כרגע רק בסופרגרופ/ערוץ (channel).")
            return
        channel_ref = peer_ref(event.peer_type, event.peer_id)
        if channel_ref is None:
            return
        rights = make_banned_rights(until_date=0)
        if await dry_run_guard(ctx=ctx, event=event, action=action_name, details=target_ref):
            return
        await ctx.app.admin.restrict(channel_ref, target_ref, rights=rights, timeout=ctx.timeout)
        ctx.storage.add_mod_log(
            peer_key=key,
            action=action_name,
            actor_id=event.sender_id,
            target_user_id=target_user_id,
            details={},
            ts=now_ts(),
        )
        if response_mode == "unmute":
            await event.reply(f"{target_ref} הוסר מהשתקה.")
            return
        await event.reply(f"הוסרו מגבלות מ-{target_ref}.")

    async def _readd_user(
        *,
        event: MessageEvent,
        target_ref: str,
        target_user_id: int,
    ) -> None:
        key = ctx.event_peer_key(event)
        if key is None:
            return
        if not _is_channel_event(event):
            await event.reply("פעולת readd נתמכת כרגע רק בסופרגרופ/ערוץ (channel).")
            return
        channel_ref = peer_ref(event.peer_type, event.peer_id)
        if channel_ref is None:
            return
        if await dry_run_guard(ctx=ctx, event=event, action="readd", details=target_ref):
            return
        ok, link, err = await try_readd_user(
            app=ctx.app,
            channel_ref=channel_ref,
            target_ref=target_ref,
            target_user_id=target_user_id,
            timeout=ctx.timeout,
        )
        if not ok:
            err_text = (err or "unknown error").strip()
            if "BOT_METHOD_INVALID" in err_text.upper():
                public_link = _public_join_link_for_event(
                    app=ctx.app,
                    peer_type=event.peer_type,
                    peer_id=event.peer_id,
                )
                ctx.storage.add_mod_log(
                    peer_key=key,
                    action="readd",
                    actor_id=event.sender_id,
                    target_user_id=target_user_id,
                    details={"mode": "manual_join_required", "reason": "bot_method_invalid"},
                    ts=now_ts(),
                )
                if public_link:
                    await event.reply(
                        "אחרי kick/ban המשתמש צריך להצטרף בעצמו.\n"
                        f"לינק הצטרפות: {public_link}"
                    )
                else:
                    await event.reply(
                        "אחרי kick/ban המשתמש צריך להצטרף בעצמו.\n"
                        "אם זו קבוצה פרטית, צור לינק הזמנה ידני ושלח למשתמש."
                    )
                return
            await event.reply(f"לא הצלחתי לבצע readd עבור {target_ref}: {err_text}")
            return
        ctx.storage.add_mod_log(
            peer_key=key,
            action="readd",
            actor_id=event.sender_id,
            target_user_id=target_user_id,
            details={"mode": "invite_link", "usage_limit": 1},
            ts=now_ts(),
        )
        await event.reply(
            "אחרי kick/ban לא ניתן לצרף משתמש בכוח.\n"
            "נוצר קישור הצטרפות זמני (שימוש אחד), המשתמש צריך להצטרף בעצמו:\n"
            f"{link}"
        )

    @router.on_message(and_(incoming(), command("warn")), stop=True)
    async def _on_warn(event: MessageEvent) -> None:
        if not await require_admin(ctx=ctx, event=event, action_name="warn"):
            return
        args = (event.command_args or "").strip()
        target_token, reason = parse_target_and_rest(args)
        if not target_token:
            await event.reply("שימוש: /warn <@user|user:id> [reason]")
            return
        try:
            target_user_id, target_ref = await resolve_user_ref(ctx, target_token)
        except Exception as ex:  # noqa: BLE001
            await event.reply(f"לא הצלחתי לפתור משתמש יעד: {ex}")
            return
        count = await _warn_user(
            event=event,
            target_user_id=target_user_id,
            reason=reason or "manual",
        )
        await event.reply(f"warning נוסף ל-{target_ref}. סה\"כ warnings={count}")
        await _maybe_auto_ban(
            event=event,
            target_user_id=target_user_id,
            count=count,
            reason="manual_warn",
        )

    @router.on_message(and_(incoming(), command("warnings")), stop=True)
    async def _on_warnings(event: MessageEvent) -> None:
        args = (event.command_args or "").strip()
        target_user_id: int | None = event.sender_id
        target_ref = f"user:{target_user_id}" if target_user_id is not None else "unknown"
        if args:
            token, _ = parse_target_and_rest(args)
            try:
                target_user_id, target_ref = await resolve_user_ref(ctx, token)
            except Exception as ex:  # noqa: BLE001
                await event.reply(f"לא הצלחתי לפתור משתמש יעד: {ex}")
                return
        if target_user_id is None:
            await event.reply("לא ניתן לזהות משתמש.")
            return
        key = ctx.event_peer_key(event)
        if key is None:
            await event.reply("peer לא מזוהה.")
            return
        count = ctx.storage.get_warning_count(peer_key=key, user_id=target_user_id)
        await event.reply(f"warnings עבור {target_ref}: {count}")

    @router.on_message(and_(incoming(), command("unwarn")), stop=True)
    async def _on_unwarn(event: MessageEvent) -> None:
        if not await require_admin(ctx=ctx, event=event, action_name="unwarn"):
            return
        args = (event.command_args or "").strip()
        target_token, _ = parse_target_and_rest(args)
        if not target_token:
            await event.reply("שימוש: /unwarn <@user|user:id>")
            return
        try:
            target_user_id, target_ref = await resolve_user_ref(ctx, target_token)
        except Exception as ex:  # noqa: BLE001
            await event.reply(f"לא הצלחתי לפתור משתמש יעד: {ex}")
            return
        key = ctx.event_peer_key(event)
        if key is None:
            await event.reply("peer לא מזוהה.")
            return
        ctx.storage.reset_warning(peer_key=key, user_id=target_user_id, ts=now_ts())
        ctx.storage.add_mod_log(
            peer_key=key,
            action="unwarn",
            actor_id=event.sender_id,
            target_user_id=target_user_id,
            details={},
            ts=now_ts(),
        )
        await event.reply(f"warnings אופסו עבור {target_ref}.")

    @router.on_message(and_(incoming(), command("restrict")), stop=True)
    async def _on_restrict(event: MessageEvent) -> None:
        if not await require_admin(ctx=ctx, event=event, action_name="restrict"):
            return
        default_minutes = max(1, int(ctx.config.auto_mute_minutes or 5))
        try:
            target_token, profile, minutes = parse_restrict_args(
                event.command_args or "",
                default_minutes=default_minutes,
            )
        except Exception as ex:  # noqa: BLE001
            await event.reply(
                "שימוש: /restrict <@user|user:id> <all|media|links|text> [minutes]\n"
                f"שגיאה: {decode_text(ex)}"
            )
            return
        try:
            target_user_id, target_ref = await resolve_user_ref(ctx, target_token)
        except Exception as ex:  # noqa: BLE001
            await event.reply(f"לא הצלחתי לפתור משתמש יעד: {decode_text(ex)}")
            return
        await _restrict_user(
            event=event,
            target_ref=target_ref,
            target_user_id=target_user_id,
            minutes=minutes,
            profile=profile,
            action_name="restrict",
            response_mode="restrict",
        )

    @router.on_message(and_(incoming(), command("unrestrict")), stop=True)
    async def _on_unrestrict(event: MessageEvent) -> None:
        if not await require_admin(ctx=ctx, event=event, action_name="unrestrict"):
            return
        target_token, _ = parse_target_and_rest(event.command_args or "")
        if not target_token:
            await event.reply("שימוש: /unrestrict <@user|user:id>")
            return
        try:
            target_user_id, target_ref = await resolve_user_ref(ctx, target_token)
        except Exception as ex:  # noqa: BLE001
            await event.reply(f"לא הצלחתי לפתור משתמש יעד: {decode_text(ex)}")
            return
        await _unrestrict_user(
            event=event,
            target_ref=target_ref,
            target_user_id=target_user_id,
            action_name="unrestrict",
            response_mode="unrestrict",
        )

    @router.on_message(and_(incoming(), command("mute")), stop=True)
    async def _on_mute(event: MessageEvent) -> None:
        if not await require_admin(ctx=ctx, event=event, action_name="mute"):
            return
        try:
            minutes, target_token = parse_minutes_target(event.command_args or "")
        except Exception:
            await event.reply("שימוש: /mute <@user|user:id> <minutes>")
            return
        if minutes <= 0:
            await event.reply("minutes חייב להיות גדול מ-0.")
            return
        try:
            target_user_id, target_ref = await resolve_user_ref(ctx, target_token)
        except Exception as ex:  # noqa: BLE001
            await event.reply(f"לא הצלחתי לפתור משתמש יעד: {ex}")
            return
        await _restrict_user(
            event=event,
            target_ref=target_ref,
            target_user_id=target_user_id,
            minutes=minutes,
            profile="all",
            action_name="mute",
            response_mode="mute",
        )

    @router.on_message(and_(incoming(), command("unmute")), stop=True)
    async def _on_unmute(event: MessageEvent) -> None:
        if not await require_admin(ctx=ctx, event=event, action_name="unmute"):
            return
        args = (event.command_args or "").strip()
        target_token, _ = parse_target_and_rest(args)
        if not target_token:
            await event.reply("שימוש: /unmute <@user|user:id>")
            return
        try:
            target_user_id, target_ref = await resolve_user_ref(ctx, target_token)
        except Exception as ex:  # noqa: BLE001
            await event.reply(f"לא הצלחתי לפתור משתמש יעד: {ex}")
            return
        await _unrestrict_user(
            event=event,
            target_ref=target_ref,
            target_user_id=target_user_id,
            action_name="unmute",
            response_mode="unmute",
        )

    @router.on_message(and_(incoming(), command("ban")), stop=True)
    async def _on_ban(event: MessageEvent) -> None:
        if not await require_admin(ctx=ctx, event=event, action_name="ban"):
            return
        if not _is_channel_event(event):
            await event.reply("ban נתמך כרגע רק בסופרגרופ/ערוץ.")
            return
        args = (event.command_args or "").strip()
        target_token, _ = parse_target_and_rest(args)
        if not target_token:
            await event.reply("שימוש: /ban <@user|user:id>")
            return
        try:
            target_user_id, target_ref = await resolve_user_ref(ctx, target_token)
        except Exception as ex:  # noqa: BLE001
            await event.reply(f"לא הצלחתי לפתור משתמש יעד: {ex}")
            return
        if await dry_run_guard(ctx=ctx, event=event, action="ban", details=target_ref):
            return
        channel_ref = peer_ref(event.peer_type, event.peer_id)
        if channel_ref is None:
            return
        await ctx.app.admin.ban(channel_ref, target_ref, timeout=ctx.timeout)
        key = ctx.event_peer_key(event)
        if key is not None:
            ctx.storage.add_mod_log(
                peer_key=key,
                action="ban",
                actor_id=event.sender_id,
                target_user_id=target_user_id,
                details={},
                ts=now_ts(),
            )
        await event.reply(f"{target_ref} נחסם.")

    @router.on_message(and_(incoming(), command("unban")), stop=True)
    async def _on_unban(event: MessageEvent) -> None:
        if not await require_admin(ctx=ctx, event=event, action_name="unban"):
            return
        if not _is_channel_event(event):
            await event.reply("unban נתמך כרגע רק בסופרגרופ/ערוץ.")
            return
        args = (event.command_args or "").strip()
        target_token, _ = parse_target_and_rest(args)
        if not target_token:
            await event.reply("שימוש: /unban <@user|user:id>")
            return
        try:
            target_user_id, target_ref = await resolve_user_ref(ctx, target_token)
        except Exception as ex:  # noqa: BLE001
            await event.reply(f"לא הצלחתי לפתור משתמש יעד: {ex}")
            return
        if await dry_run_guard(ctx=ctx, event=event, action="unban", details=target_ref):
            return
        channel_ref = peer_ref(event.peer_type, event.peer_id)
        if channel_ref is None:
            return
        await ctx.app.admin.unban(channel_ref, target_ref, timeout=ctx.timeout)
        key = ctx.event_peer_key(event)
        if key is not None:
            ctx.storage.add_mod_log(
                peer_key=key,
                action="unban",
                actor_id=event.sender_id,
                target_user_id=target_user_id,
                details={},
                ts=now_ts(),
            )
        await event.reply(f"{target_ref} שוחרר מחסימה.")

    @router.on_message(and_(incoming(), command("kick")), stop=True)
    async def _on_kick(event: MessageEvent) -> None:
        if not await require_admin(ctx=ctx, event=event, action_name="kick"):
            return
        if not _is_channel_event(event):
            await event.reply("kick נתמך כרגע רק בסופרגרופ/ערוץ.")
            return
        args = (event.command_args or "").strip()
        target_token, _ = parse_target_and_rest(args)
        if not target_token:
            await event.reply("שימוש: /kick <@user|user:id>")
            return
        try:
            target_user_id, target_ref = await resolve_user_ref(ctx, target_token)
        except Exception as ex:  # noqa: BLE001
            await event.reply(f"לא הצלחתי לפתור משתמש יעד: {ex}")
            return
        if await dry_run_guard(ctx=ctx, event=event, action="kick", details=target_ref):
            return
        channel_ref = peer_ref(event.peer_type, event.peer_id)
        if channel_ref is None:
            return
        await ctx.app.admin.kick(channel_ref, target_ref, timeout=ctx.timeout)
        key = ctx.event_peer_key(event)
        if key is not None:
            ctx.storage.add_mod_log(
                peer_key=key,
                action="kick",
                actor_id=event.sender_id,
                target_user_id=target_user_id,
                details={},
                ts=now_ts(),
            )
        await event.reply(f"{target_ref} הוצא מהקבוצה.")

    @router.on_message(and_(incoming(), command("readd")), stop=True)
    async def _on_readd(event: MessageEvent) -> None:
        if not await require_admin(ctx=ctx, event=event, action_name="readd"):
            return
        if not _is_channel_event(event):
            await event.reply("readd נתמך כרגע רק בסופרגרופ/ערוץ.")
            return
        target_token, _ = parse_target_and_rest(event.command_args or "")
        if not target_token:
            await event.reply("שימוש: /readd <@user|user:id>")
            return
        try:
            target_user_id, target_ref = await resolve_user_ref(ctx, target_token)
        except Exception as ex:  # noqa: BLE001
            await event.reply(f"לא הצלחתי לפתור משתמש יעד: {decode_text(ex)}")
            return
        await _readd_user(
            event=event,
            target_ref=target_ref,
            target_user_id=target_user_id,
        )

    @router.on_message(incoming(), stop=False)
    async def _on_policy_checks(event: MessageEvent) -> None:
        text = (event.text or "").strip()
        if not text:
            return
        if event.sender_id is None:
            return
        if event.command is not None:
            return
        key = ctx.event_peer_key(event)
        if key is None:
            return
        is_admin = await ctx.is_admin(
            peer_type=event.peer_type,
            peer_id=event.peer_id,
            user_id=event.sender_id,
        )
        if is_admin:
            return

        current_rate = ctx.track_flood(peer_key=key, user_id=int(event.sender_id))
        flood_threshold = max(2, int(ctx.config.flood_message_count))
        if current_rate >= flood_threshold:
            if not ctx.flood_on_cooldown(peer_key=key, user_id=int(event.sender_id)):
                ctx.mark_flood_action(peer_key=key, user_id=int(event.sender_id))
                count = await _warn_user(
                    event=event,
                    target_user_id=int(event.sender_id),
                    reason=f"anti_flood:{current_rate}",
                )
                await event.reply(
                    f"אזהרה: זוהה flood (messages={current_rate}). "
                    f"warnings={count}/{ctx.config.warn_threshold}"
                )
                if ctx.config.auto_mute_minutes > 0:
                    target_ref = f"user:{int(event.sender_id)}"
                    await _restrict_user(
                        event=event,
                        target_ref=target_ref,
                        target_user_id=int(event.sender_id),
                        minutes=int(ctx.config.auto_mute_minutes),
                        profile="all",
                        action_name="auto_mute",
                        response_mode="mute",
                    )
                await _maybe_auto_ban(
                    event=event,
                    target_user_id=int(event.sender_id),
                    count=count,
                    reason="anti_flood",
                )
            return

        violation_reason: str | None = None
        if ctx.config.block_links and has_link(text):
            violation_reason = "links"
        else:
            token = has_blocked_keyword(text, ctx.config.blocked_keywords)
            if token is not None:
                violation_reason = f"keyword:{token}"

        if violation_reason is None:
            return

        count = await _warn_user(
            event=event,
            target_user_id=int(event.sender_id),
            reason=violation_reason,
        )
        details = f"user:{event.sender_id} reason={violation_reason}"
        if await dry_run_guard(ctx=ctx, event=event, action="content-violation", details=details):
            await event.reply(f"[dry-run] הודעה זוהתה כהפרת מדיניות ({violation_reason}).")
            return

        ref = peer_ref(event.peer_type, event.peer_id)
        if ref is not None and event.msg_id is not None:
            try:
                await ctx.app.messages.delete(
                    ref,
                    [int(event.msg_id)],
                    revoke=True,
                    timeout=ctx.timeout,
                )
            except Exception:
                pass

        await event.reply(
            f"הודעה נחסמה ({violation_reason}). warnings={count}/{ctx.config.warn_threshold}"
        )
        await _maybe_auto_ban(
            event=event,
            target_user_id=int(event.sender_id),
            count=count,
            reason=violation_reason,
        )


async def teardown(router: Router) -> None:
    _ = router
