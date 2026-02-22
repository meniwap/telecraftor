from __future__ import annotations

import argparse
import asyncio
import logging
import os
from pathlib import Path

from telecraft.bot import (
    CallbackQueryEvent,
    Dispatcher,
    MessageEvent,
    Router,
    callback_data_startswith,
    incoming,
    text,
)
from telecraft.client import Client, ClientInit
from telecraft.client.keyboards import InlineKeyboard
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
    p = argparse.ArgumentParser(description="Telecraft MTProto bot keyboard demo")
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
    p.add_argument("--session", type=str, default=None, help="Explicit bot session path")
    p.add_argument("--dc", type=int, default=2, help="Preferred DC for bot session auto-discovery")
    p.add_argument(
        "--target",
        type=str,
        default=os.environ.get("TELECRAFT_BOT_DEMO_TARGET"),
        help="Optional target (@username / user:ID / chat:ID / channel:ID) to send demo on startup",
    )
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
                action="bot keyboard demo on production Telegram",
                example=(
                    "TELECRAFT_ALLOW_PROD=1 ./.venv/bin/python apps/bot_keyboard_demo.py "
                    "--runtime prod --allow-prod"
                ),
            )
        session_paths = resolve_session_paths(runtime=runtime, network=network)
        if args.session:
            session_path = str(Path(args.session).expanduser().resolve())
        else:
            session_path = pick_existing_session(
                session_paths,
                preferred_dc=int(args.dc),
                kind="bot",
            )
        session_obj = Path(session_path).expanduser().resolve()
        if not session_obj.exists():
            raise SystemExit(
                f"No bot session found for runtime={runtime!r} network={network!r}. "
                "Run: ./.venv/bin/python apps/run.py login-bot --runtime sandbox"
            )
        validate_session_matches_network(session_path=session_obj, expected_network=network)
        return runtime, network, str(session_obj)
    except RuntimeIsolationError as e:
        raise SystemExit(str(e)) from e


def _peer_ref_from_event(peer_type: str | None, peer_id: int | None) -> str | None:
    if peer_type is None or peer_id is None:
        return None
    return f"{peer_type}:{int(peer_id)}"


async def main(args: argparse.Namespace) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    api_id = int(_need("TELEGRAM_API_ID"))
    api_hash = _need("TELEGRAM_API_HASH")
    runtime, network, session = _resolve_runtime_session(args)
    print(f"Using runtime={runtime} network={network} bot_session={session}")

    app = Client(
        network=network,
        session_path=session,
        init=ClientInit(api_id=api_id, api_hash=api_hash),
    )
    await app.connect()
    print("Bot keyboard demo started. Send /start to the bot and click Yes/No.")

    router = Router()

    async def send_cat_prompt(peer: str) -> None:
        kb = InlineKeyboard()
        kb.button("כן", callback_data="cat_yes").button("לא", callback_data="cat_no")
        await app.messages.send(peer, "אני חתול", reply_markup=kb.build())

    @router.on_message(incoming(), stop=False)
    async def _trace(e: MessageEvent) -> None:
        if e.text:
            print(
                f"IN: peer={e.peer_type}:{e.peer_id} sender={e.sender_id} msg_id={e.msg_id} text={e.text!r}"
            )

    @router.on_message(text(), stop=True)
    async def _on_start(e: MessageEvent) -> None:
        if (e.text or "").strip().lower().startswith("/start"):
            peer = _peer_ref_from_event(e.peer_type, e.peer_id)
            if peer is not None:
                await send_cat_prompt(peer)

    @router.on_callback_query(callback_data_startswith("cat_"), stop=True)
    async def _on_cat_callback(e: CallbackQueryEvent) -> None:
        choice = (e.data_text or "").strip()
        if choice == "cat_yes":
            picked = "כן"
            toast = "מיאו 😸"
        else:
            picked = "לא"
            toast = "מיאו? 😿"
        await e.answer(message=toast, alert=False, cache_time=0)

        peer = _peer_ref_from_event(e.peer_type, e.peer_id)
        if peer is not None and e.msg_id is not None:
            await app.messages.send(peer, f"נקלטה לחיצה: {picked}")
            try:
                await app.messages.edit(peer, int(e.msg_id), f"אני חתול — בחרת: {picked}")
            except Exception as ex:  # noqa: BLE001
                print(f"edit failed: {type(ex).__name__}: {ex}")

    if args.target:
        try:
            await send_cat_prompt(str(args.target))
            print(f"Sent startup demo to {args.target}")
        except Exception as ex:  # noqa: BLE001
            print(f"startup send failed: {type(ex).__name__}: {ex}")

    disp = Dispatcher(
        client=app.raw,
        router=router,
        ignore_outgoing=True,
        ignore_before_start=True,
        backlog_policy="process_no_reply",
        backlog_grace_seconds=60,
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
