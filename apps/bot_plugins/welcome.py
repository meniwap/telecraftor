from __future__ import annotations

from bot_plugins.shared import ctx_from_router
from telecraft.bot import (
    ChatActionEvent,
    MemberUpdateEvent,
    Router,
    action_join,
    action_leave,
    member_banned,
    member_left,
    member_promoted,
)


def _member_kind_line(event: MemberUpdateEvent) -> str:
    return (
        f"member_update kind={event.kind} peer={event.peer_type}:{event.peer_id} "
        f"actor={event.actor_id} user={event.user_id}"
    )


async def setup(router: Router) -> None:
    ctx = ctx_from_router(router)
    if not ctx.config.enable_welcome:
        return

    @router.on_action(action_join(), stop=False)
    async def _on_join(event: ChatActionEvent) -> None:
        users = event.added_user_ids or []
        if users:
            suffix = ", ".join(str(uid) for uid in users[:5])
        else:
            suffix = str(event.sender_id) if event.sender_id is not None else "unknown"
        await event.reply(f"ברוכים הבאים 👋 ({suffix})")
        key = ctx.event_peer_key(event)
        if key is not None:
            await ctx.send_audit(f"[JOIN] peer={key} users={suffix}")

    @router.on_action(action_leave(), stop=False)
    async def _on_leave(event: ChatActionEvent) -> None:
        target = (
            event.removed_user_id
            if event.removed_user_id is not None
            else (event.sender_id if event.sender_id is not None else "unknown")
        )
        await event.reply(f"להתראות 👋 ({target})")
        key = ctx.event_peer_key(event)
        if key is not None:
            await ctx.send_audit(f"[LEAVE] peer={key} user={target}")

    @router.on_member_update(member_promoted(), stop=False)
    async def _on_member_promoted(event: MemberUpdateEvent) -> None:
        await ctx.send_audit(f"[PROMOTE] {_member_kind_line(event)}")

    @router.on_member_update(member_banned(), stop=False)
    async def _on_member_banned(event: MemberUpdateEvent) -> None:
        await ctx.send_audit(f"[BAN] {_member_kind_line(event)}")

    @router.on_member_update(member_left(), stop=False)
    async def _on_member_left(event: MemberUpdateEvent) -> None:
        await ctx.send_audit(f"[MEMBER_LEFT] {_member_kind_line(event)}")


async def teardown(router: Router) -> None:
    _ = router
