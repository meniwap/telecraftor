from __future__ import annotations

import argparse
import asyncio
import logging
import os
from pathlib import Path

from telecraft.bot import (
    ChatActionEvent,
    DeletedMessagesEvent,
    Dispatcher,
    MemberUpdateEvent,
    MessageEvent,
    ReactionEvent,
    Router,
    action_join,
    action_leave,
    action_pin,
    action_title,
    edited_message,
    has_media,
    incoming,
    member_banned,
    member_joined,
    member_left,
    member_promoted,
    new_message,
    private,
    reply_to,
)
from telecraft.client import Client, ClientInit
from telecraft.client.runtime_isolation import (
    RuntimeIsolationError,
    pick_existing_session,
    require_prod_override,
    resolve_network,
    resolve_runtime,
    resolve_session_paths,
    validate_session_matches_network,
)


def _try_load_env_file(path: str) -> None:
    p = Path(path)
    if not p.exists():
        return
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip("'").strip('"')
        if k and k not in os.environ:
            os.environ[k] = v


def _need(name: str) -> str:
    if name not in os.environ:
        _try_load_env_file("apps/env.sh")
    v = os.environ.get(name)
    if not v:
        raise SystemExit(f"Missing {name}. Run: source apps/env.sh")
    return v


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Telecraft selftest bot")
    p.add_argument(
        "--runtime",
        choices=["sandbox", "prod"],
        default=os.environ.get("TELECRAFT_RUNTIME", "sandbox"),
        help="Runtime lane (default: sandbox)",
    )
    p.add_argument(
        "--allow-prod",
        action="store_true",
        default=False,
        help="Allow production runtime (requires TELECRAFT_ALLOW_PROD=1)",
    )
    p.add_argument(
        "--network",
        choices=["test", "prod"],
        default=None,
        help="Deprecated override; runtime determines network",
    )
    p.add_argument("--session", type=str, default=None, help="Explicit session path")
    p.add_argument("--dc", type=int, default=2, help="Preferred DC for session auto-discovery")
    return p.parse_args()


def _resolve_runtime_session(args: argparse.Namespace) -> tuple[str, str, str]:
    try:
        runtime = resolve_runtime(str(args.runtime), default="sandbox")
        if args.network:
            print("Warning: --network is deprecated; use --runtime sandbox|prod.")
        network = resolve_network(runtime=runtime, explicit_network=args.network)
        if runtime == "prod":
            require_prod_override(
                allow_flag=bool(args.allow_prod),
                env_var="TELECRAFT_ALLOW_PROD",
                action="selftest bot on production Telegram",
                example=(
                    "TELECRAFT_ALLOW_PROD=1 ./.venv/bin/python apps/selftest_bot.py "
                    "--runtime prod --allow-prod"
                ),
            )
        session_paths = resolve_session_paths(runtime=runtime, network=network)
        if args.session:
            session_path = str(Path(args.session).expanduser().resolve())
        else:
            session_path = pick_existing_session(session_paths, preferred_dc=int(args.dc))
        session_obj = Path(session_path).expanduser().resolve()
        if not session_obj.exists():
            raise SystemExit(
                f"No session found for runtime={runtime!r} network={network!r}. "
                "Run: ./.venv/bin/python apps/run.py login --runtime sandbox"
            )
        validate_session_matches_network(session_path=session_obj, expected_network=network)
        return runtime, network, str(session_obj)
    except RuntimeIsolationError as e:
        raise SystemExit(str(e)) from e

def _env_bool(name: str, default: bool = False) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "y", "on"}

def _env_int(name: str, default: int) -> int:
    v = os.environ.get(name)
    if v is None or not v.strip():
        return default
    try:
        return int(v.strip())
    except ValueError:
        return default


async def main(args: argparse.Namespace) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    api_id = int(_need("TELEGRAM_API_ID"))
    api_hash = _need("TELEGRAM_API_HASH")
    runtime, network, session = _resolve_runtime_session(args)
    print(f"Using runtime={runtime} network={network} session={session}")

    app = Client(
        network=network,
        session_path=session,
        init=ClientInit(api_id=api_id, api_hash=api_hash),
    )
    await app.connect()
    client = app.raw
    print("Selftest bot started. Ctrl+C to stop.")
    print("")
    print("### What to test (manual):")
    print(
        "- Send a DM to yourself from another account OR ask a friend to DM you "
        "-> should trigger NEW message handler"
    )
    print("- Send a photo in DM -> should trigger HAS_MEDIA handler")
    print("- Reply to a message in DM -> should trigger REPLY_TO handler")
    print("- Edit a message you sent in DM -> should trigger EDIT handler (kind='edit')")
    print("- Add a reaction (❤️) to a message -> should print a [REACTION] line")
    print(
        "- Delete a message you sent -> should print a [DELETED] line "
        "(peer may be unknown for non-channel)"
    )
    print("")
    print("### Group/service actions (manual, in a group/supergroup):")
    print("- Add this account to a group / someone joins -> should print [ACTION] kind=join")
    print("- Remove a member / someone leaves -> should print [ACTION] kind=leave")
    print("- Pin a message -> should print [ACTION] kind=pin")
    print("- Change group title -> should print [ACTION] kind=title")
    print("")
    print("### Member updates (manual, in a group/supergroup):")
    print("- Promote someone to admin -> should print [MEMBER] kind=promote")
    print("- Ban/kick someone (supergroup/channel) -> should print [MEMBER] kind=ban/kick")
    print("")

    router = Router()

    async def notify_peer(peer_type: str | None, peer_id: int | None, text: str) -> None:
        if peer_type == "chat" and peer_id is not None:
            await client.send_message_chat(int(peer_id), text)
            return
        if peer_type == "channel" and peer_id is not None:
            await client.send_message_channel(int(peer_id), text)
            return
        if peer_type == "user" and peer_id is not None:
            await client.send_message_user(int(peer_id), text)
            return
        await client.send_message_self(text)

    @router.on_message(incoming())
    async def any_incoming(e: MessageEvent) -> None:
        # This runs first for every incoming message we map.
        print(
            f"[INCOMING] kind={e.kind} peer={e.peer_type}:{e.peer_id} "
            f"sender={e.sender_id} msg_id={e.msg_id} text={e.text!r}"
        )

    # Use stop=True so a single message doesn't trigger multiple replies.
    @router.on_message(reply_to(), stop=True)
    async def on_reply(e: MessageEvent) -> None:
        await e.reply(f"selftest: reply_to OK (reply_to_msg_id={e.reply_to_msg_id})")

    @router.on_message(has_media(), stop=True)
    async def on_media(e: MessageEvent) -> None:
        await e.reply("selftest: media OK")

    @router.on_message(edited_message(), stop=True)
    async def on_edit(e: MessageEvent) -> None:
        await e.reply("selftest: edit OK")

    @router.on_message(new_message(), stop=True)
    async def on_new(e: MessageEvent) -> None:
        # New messages only (dispatcher should ignore backlog before start).
        if e.text:
            await e.reply("selftest: new message OK")

    @router.on_reaction()
    async def on_reaction(e: ReactionEvent) -> None:
        print(
            f"[REACTION] peer={e.peer_type}:{e.peer_id} msg_id={e.msg_id} "
            f"reactions={type(e.reactions).__name__} "
            f"counts={getattr(e, 'counts', {})} my={getattr(e, 'my_reactions', [])}"
        )
        if not getattr(e, "is_backlog", False):
            await notify_peer(e.peer_type, e.peer_id, f"selftest: reaction OK (msg_id={e.msg_id})")

    @router.on_deleted_messages()
    async def on_deleted(e: DeletedMessagesEvent) -> None:
        print(f"[DELETED] peer={e.peer_type}:{e.peer_id} msg_ids={e.msg_ids}")
        if not getattr(e, "is_backlog", False):
            await notify_peer(e.peer_type, e.peer_id, f"selftest: delete OK (ids={e.msg_ids})")

    @router.on_member_update(member_joined())
    async def on_member_joined(e: MemberUpdateEvent) -> None:
        print(
            f"[MEMBER] kind={e.kind} peer={e.peer_type}:{e.peer_id} actor={e.actor_id} "
            f"user={e.user_id} qts={e.qts}"
        )

    @router.on_member_update(member_left())
    async def on_member_left(e: MemberUpdateEvent) -> None:
        print(
            f"[MEMBER] kind={e.kind} peer={e.peer_type}:{e.peer_id} actor={e.actor_id} "
            f"user={e.user_id} qts={e.qts}"
        )

    @router.on_member_update(member_promoted())
    async def on_member_promoted(e: MemberUpdateEvent) -> None:
        print(
            f"[MEMBER] kind={e.kind} peer={e.peer_type}:{e.peer_id} actor={e.actor_id} "
            f"user={e.user_id} qts={e.qts}"
        )

    @router.on_member_update(member_banned())
    async def on_member_banned(e: MemberUpdateEvent) -> None:
        print(
            f"[MEMBER] kind={e.kind} peer={e.peer_type}:{e.peer_id} actor={e.actor_id} "
            f"user={e.user_id} qts={e.qts}"
        )

    # Catch-all: helps diagnose why specific member kinds don't fire.
    @router.on_member_update()
    async def on_member_any(e: MemberUpdateEvent) -> None:
        prev = getattr(getattr(e, "prev_participant", None), "TL_NAME", None)
        new = getattr(getattr(e, "new_participant", None), "TL_NAME", None)
        raw = getattr(getattr(e, "raw", None), "TL_NAME", None)
        print(
            f"[MEMBER*] raw={raw} kind={e.kind} peer={e.peer_type}:{e.peer_id} "
            f"actor={e.actor_id} user={e.user_id} prev={prev} new={new} qts={e.qts}"
        )

    @router.on_action(action_join(), stop=True)
    async def on_join(e: ChatActionEvent) -> None:
        print(
            f"[ACTION] msg_id={e.msg_id} kind={e.kind} peer={e.peer_type}:{e.peer_id} "
            f"sender={e.sender_id} inviter_id={e.inviter_id} added={e.added_user_ids}"
        )
        await e.reply("selftest: action join OK")

    @router.on_action(action_leave(), stop=True)
    async def on_leave(e: ChatActionEvent) -> None:
        print(
            f"[ACTION] msg_id={e.msg_id} kind={e.kind} peer={e.peer_type}:{e.peer_id} "
            f"sender={e.sender_id} removed={e.removed_user_id}"
        )
        await e.reply("selftest: action leave OK")

    @router.on_action(action_pin(), stop=True)
    async def on_pin(e: ChatActionEvent) -> None:
        print(
            f"[ACTION] msg_id={e.msg_id} kind={e.kind} peer={e.peer_type}:{e.peer_id} "
            f"sender={e.sender_id} pinned_msg_id={e.pinned_msg_id}"
        )
        await e.reply("selftest: action pin OK")

    @router.on_action(action_title(), stop=True)
    async def on_title(e: ChatActionEvent) -> None:
        print(
            f"[ACTION] msg_id={e.msg_id} kind={e.kind} peer={e.peer_type}:{e.peer_id} "
            f"sender={e.sender_id} title={e.new_title!r}"
        )
        await e.reply("selftest: action title OK")

    @router.on_message(private())
    async def on_private(e: MessageEvent) -> None:
        # Example: show command parsing when DM text starts with /
        if e.command:
            await e.reply(f"selftest: command={e.command!r} args={e.command_args!r}")

    # Keep grace small so we don't respond to backlog when the process restarts.
    trace = _env_bool("SELFTEST_TRACE", False)
    disp = Dispatcher(
        client=client,
        router=router,
        debug=_env_bool("SELFTEST_DEBUG", False) or trace,
        ignore_outgoing=_env_bool("SELFTEST_IGNORE_OUTGOING", True) if not trace else False,
        backlog_grace_seconds=2,
        backlog_policy="process_no_reply",
        throttle_peer_per_minute=_env_int("SELFTEST_THROTTLE_PEER_PER_MIN", 20),
        throttle_global_per_minute=_env_int("SELFTEST_THROTTLE_GLOBAL_PER_MIN", 120),
        throttle_burst=10,
        trace_all_updates=_env_bool("SELFTEST_TRACE_ALL", False),
        trace_update_substrings=("Participant",) if trace else (),
        trace_update_names=(
            "updateChatParticipant",
            "updateChannelParticipant",
            "updateChatParticipantAdd",
            "updateChatParticipantDelete",
            "updateChatParticipantAdmin",
        )
        if trace
        else (),
    )
    try:
        await disp.run()
    finally:
        await app.close()


if __name__ == "__main__":
    try:
        asyncio.run(main(_parse_args()))
    except KeyboardInterrupt:
        pass
