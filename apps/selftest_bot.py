from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from telecraft.bot import (
    Dispatcher,
    MessageEvent,
    Router,
    edited_message,
    has_media,
    incoming,
    new_message,
    private,
    reply_to,
)
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
    print("")

    router = Router()

    @router.on_message(incoming())
    async def any_incoming(e: MessageEvent) -> None:
        # This runs first for every incoming message we map.
        print(
            f"[INCOMING] kind={e.kind} peer={e.peer_type}:{e.peer_id} "
            f"sender={e.sender_id} msg_id={e.msg_id} text={e.text!r}"
        )

    @router.on_message(new_message())
    async def on_new(e: MessageEvent) -> None:
        # New messages only (incl. backlog, but dispatcher filters old messages by default).
        if e.text:
            await e.reply("selftest: new message OK")

    @router.on_message(edited_message())
    async def on_edit(e: MessageEvent) -> None:
        await e.reply("selftest: edit OK")

    @router.on_message(has_media())
    async def on_media(e: MessageEvent) -> None:
        await e.reply("selftest: media OK")

    @router.on_message(reply_to())
    async def on_reply(e: MessageEvent) -> None:
        await e.reply(f"selftest: reply_to OK (reply_to_msg_id={e.reply_to_msg_id})")

    @router.on_message(private())
    async def on_private(e: MessageEvent) -> None:
        # Example: show command parsing when DM text starts with /
        if e.command:
            await e.reply(f"selftest: command={e.command!r} args={e.command_args!r}")

    disp = Dispatcher(client=client, router=router, debug=False)
    try:
        await disp.run()
    finally:
        await client.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass


