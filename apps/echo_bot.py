from __future__ import annotations

import asyncio
import os
from pathlib import Path

from telecraft.bot import Dispatcher, MessageEvent, Router, text
from telecraft.client.mtproto import ClientInit, MtprotoClient


def _try_load_env_file(path: str) -> None:
    """
    Best-effort loader for apps/env.sh so users can run:
      ./.venv/bin/python apps/echo_bot.py
    without needing to `source apps/env.sh` first.
    """
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
    print("Echo bot started. Send me a message (DM/basic group/channel). Ctrl+C to stop.")

    router = Router()

    @router.on_message(text())
    async def echo(e: MessageEvent) -> None:
        # Best-effort echo:
        # - basic groups: reply to chat_id
        # - DMs/channels: reply if access_hash is available (Dispatcher primes dialogs)
        # - fallback: Saved Messages
        if e.text:
            # Prevent echo-loops if we also process outgoing messages.
            if e.text.startswith("echo: "):
                return
            print(
                f"IN: chat_id={e.chat_id} channel_id={e.channel_id} "
                f"user_id={e.user_id} text={e.text!r}"
            )
            await e.reply("echo: " + e.text)

    # For easier local testing, allow processing outgoing messages too.
    # The handler above prevents loops by ignoring messages that already start with "echo: ".
    disp = Dispatcher(client=client, router=router, ignore_outgoing=False, debug=True)
    try:
        await disp.run()
    finally:
        await client.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

