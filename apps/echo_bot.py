from __future__ import annotations

import asyncio
import os
from pathlib import Path

from telecraft.bot import Dispatcher, MessageEvent, Router, text
from telecraft.client.mtproto import ClientInit, MtprotoClient


def _need(name: str) -> str:
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
    api_id = int(_need("TELEGRAM_API_ID"))
    api_hash = _need("TELEGRAM_API_HASH")

    session = _current_session_path("prod")
    client = MtprotoClient(
        network="prod",
        session_path=session,
        init=ClientInit(api_id=api_id, api_hash=api_hash),
    )
    await client.connect()

    router = Router()

    @router.on_message(text())
    async def echo(e: MessageEvent) -> None:
        # Best-effort echo:
        # - basic groups: reply to chat_id
        # - DMs/channels: reply if access_hash is available (Dispatcher primes dialogs)
        # - fallback: Saved Messages
        if e.text:
            await e.reply("echo: " + e.text)

    disp = Dispatcher(client=client, router=router)
    try:
        await disp.run()
    finally:
        await client.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

