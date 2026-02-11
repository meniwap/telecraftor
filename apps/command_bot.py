from __future__ import annotations

import argparse
import asyncio
import logging
import os
from pathlib import Path

from telecraft.bot import (
    MessageEvent,
    ReconnectPolicy,
    Router,
    and_,
    command,
    outgoing,
    run_userbot,
    text,
)
from telecraft.client import Client, ClientInit
from telecraft.client.mtproto import MtprotoClient
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
    p = argparse.ArgumentParser(description="Telecraft command bot")
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
                action="command bot on production Telegram",
                example=(
                    "TELECRAFT_ALLOW_PROD=1 ./.venv/bin/python apps/command_bot.py "
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
    try:
        me = await app.profile.me()
        mid = getattr(me, "id", None)
        print(f"Me: id={mid} self_user_id={client.self_user_id}")
    except Exception as ex:  # noqa: BLE001
        print(f"Warning: get_me failed: {type(ex).__name__}: {ex}")
    print("Command bot started. Try sending: /ping  or  /send @username hi")

    router = Router()

    @router.on_message(text(), stop=False)
    async def trace_messages(e: MessageEvent) -> None:
        if e.text:
            direction = "OUT" if e.outgoing else "IN"
            print(
                f"[{direction}] peer={e.peer_type}:{e.peer_id} "
                f"sender={e.sender_id} text={e.text!r}"
            )

    # Userbot-style commands: trigger on outgoing messages you type yourself.
    @router.on_message(and_(outgoing(), command("ping")), stop=True)
    async def on_ping(e: MessageEvent) -> None:
        await e.reply("pong")

    @router.on_message(and_(outgoing(), command("send")), stop=True)
    async def on_send(e: MessageEvent) -> None:
        # Usage: /send @username hello there
        args = (e.command_args or "").strip()
        if not args:
            await e.reply("Usage: /send @username hello")
            return
        head, _, rest = args.partition(" ")
        target = head.strip()
        msg = rest.strip()
        if not target or not msg:
            await e.reply("Usage: /send @username hello")
            return

        await app.messages.send(target, msg)
        await e.reply("sent")

    @router.on_message(and_(outgoing(), command("add")), stop=True)
    async def on_add(e: MessageEvent) -> None:
        # Usage:
        #   /add @username
        # Adds a user to the current chat/channel (requires admin rights + user privacy permitting).
        args = (e.command_args or "").strip()
        if not args:
            await e.reply("Usage: /add @username")
            return
        target = args.split(" ", 1)[0].strip()
        if not target:
            await e.reply("Usage: /add @username")
            return
        try:
            await e.add_user(target)
            await e.reply("added")
        except Exception as ex:  # noqa: BLE001
            await e.reply(f"add failed: {type(ex).__name__}: {ex}")

    def make_disp(c: MtprotoClient, r: Router):
        # Local import to keep types simple for examples.
        from telecraft.bot import Dispatcher

        return Dispatcher(
            client=c,
            router=r,
            # We want to process outgoing commands typed by the user (userbot UX).
            ignore_outgoing=False,
            ignore_before_start=True,
            backlog_grace_seconds=5,
            # Avoid replaying old outgoing commands after reconnect/startup.
            backlog_policy="ignore",
            debug=True,
        )

    await run_userbot(
        client=app.raw,
        router=router,
        make_dispatcher=make_disp,
        reconnect=ReconnectPolicy(enabled=True, initial_delay_seconds=1.0, max_delay_seconds=30.0),
    )


if __name__ == "__main__":
    try:
        asyncio.run(main(_parse_args()))
    except KeyboardInterrupt:
        pass
