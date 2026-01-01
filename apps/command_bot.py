from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from telecraft.bot import MessageEvent, ReconnectPolicy, Router, command, incoming, run_userbot
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
    print("Command bot started. Try sending: /ping  or  /send @username hi")

    router = Router()

    @router.on_message(incoming(), stop=False)
    async def trace_incoming(e: MessageEvent) -> None:
        if e.text:
            print(f"[IN] peer={e.peer_type}:{e.peer_id} sender={e.sender_id} text={e.text!r}")

    @router.on_message(command("ping"), stop=True)
    async def on_ping(e: MessageEvent) -> None:
        await e.reply("pong")

    @router.on_message(command("send"), stop=True)
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

    def make_disp(c: MtprotoClient, r: Router):
        # Local import to keep types simple for examples.
        from telecraft.bot import Dispatcher

        return Dispatcher(
            client=c,
            router=r,
            ignore_outgoing=True,
            ignore_before_start=True,
            backlog_grace_seconds=5,
            backlog_policy="process_no_reply",
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


