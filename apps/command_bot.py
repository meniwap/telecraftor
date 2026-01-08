from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from telecraft.bot import MessageEvent, ReconnectPolicy, Router, and_, command, outgoing, run_userbot, text
from telecraft.client.mtproto import ClientInit, MtprotoClient


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


def _current_session_path(network: str) -> str:
    p = Path(".sessions") / f"{network}.current"
    if p.exists():
        s = p.read_text(encoding="utf-8").strip()
        if s and Path(s).exists():
            return s
    raise SystemExit("No session found. Run: ./.venv/bin/python apps/run.py login")


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    api_id = int(_need("TELEGRAM_API_ID"))
    api_hash = _need("TELEGRAM_API_HASH")
    session = _current_session_path("prod")
    print(f"Using session: {session}")

    client = MtprotoClient(
        network="prod",
        session_path=session,
        init=ClientInit(api_id=api_id, api_hash=api_hash),
    )
    await client.connect()
    try:
        me = await client.get_me()
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
            print(f"[{direction}] peer={e.peer_type}:{e.peer_id} sender={e.sender_id} text={e.text!r}")

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

        await client.send_message(target, msg)
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
        client=client,
        router=router,
        make_dispatcher=make_disp,
        reconnect=ReconnectPolicy(enabled=True, initial_delay_seconds=1.0, max_delay_seconds=30.0),
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass


