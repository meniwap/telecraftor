from __future__ import annotations

import argparse
import asyncio
import logging
import os
from pathlib import Path

from telecraft.bot import Dispatcher, MessageEvent, Router, text
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


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Telecraft echo bot")
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
                action="echo bot on production Telegram",
                example=(
                    "TELECRAFT_ALLOW_PROD=1 ./.venv/bin/python apps/echo_bot.py "
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
    print("Echo bot started. Send me a message (DM/basic group/channel). Ctrl+C to stop.")

    router = Router()

    # Example:
    #   @router.on_message(text())
    #   async def echo(e): ...
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

    # Defaults:
    # - ignore_outgoing=True: behave like a "real bot" (react only to incoming messages)
    # - allow overriding for testing via TELECRAFT_ECHO_ALLOW_OUTGOING=1
    allow_outgoing = os.environ.get("TELECRAFT_ECHO_ALLOW_OUTGOING", "").strip() in {
        "1",
        "true",
        "yes",
    }
    disp = Dispatcher(
        client=client,
        router=router,
        ignore_outgoing=not allow_outgoing,
        ignore_before_start=True,
        backlog_grace_seconds=600,
        debug=True,
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
