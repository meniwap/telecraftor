from __future__ import annotations

import argparse
import asyncio
import logging
import os
from pathlib import Path
from typing import Any

from telecraft.bot import (
    Dispatcher,
    PluginLoader,
    ReconnectPolicy,
    Router,
    StopPropagation,
    run_userbot,
)
from telecraft.bot.groupbot import (
    GroupBotContext,
    GroupBotStorage,
    attach_group_bot_context,
    load_group_bot_config,
)
from telecraft.bot.scheduler import Scheduler
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
    p = argparse.ArgumentParser(description="Telecraft MTProto group bot")
    p.add_argument(
        "--config",
        type=str,
        default="apps/bot_config.json",
        help="Path to group-bot JSON config",
    )
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
    p.add_argument("--dc", type=int, default=2, help="Preferred DC for bot-session auto-discovery")
    p.add_argument("--timeout", type=float, default=30.0, help="Default timeout seconds")
    p.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging verbosity",
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
                action="group bot on production Telegram",
                example=(
                    "TELECRAFT_ALLOW_PROD=1 ./.venv/bin/python apps/group_bot.py "
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


def _default_plugin_paths() -> list[str]:
    return [
        "apps/bot_plugins/core.py",
        "apps/bot_plugins/moderation.py",
        "apps/bot_plugins/welcome.py",
        "apps/bot_plugins/utilities.py",
        "apps/bot_plugins/stats.py",
    ]


def _resolve_plugin_paths(config_path: Path, configured: list[str]) -> list[Path]:
    base = config_path.parent.resolve()
    raw_paths = configured or _default_plugin_paths()
    out: list[Path] = []
    for item in raw_paths:
        p = Path(item).expanduser()
        if not p.is_absolute():
            candidate = (Path.cwd() / p).resolve()
            if candidate.exists():
                p = candidate
            else:
                p = (base / p).resolve()
        out.append(p)
    return out


def _as_int_or_none(value: int | None) -> int | None:
    if value is None:
        return None
    if int(value) <= 0:
        return None
    return int(value)


def _install_scope_middlewares(router: Router, *, ctx: GroupBotContext) -> None:
    async def _guard(event: Any, nxt: Any) -> None:
        peer_type = getattr(event, "peer_type", None)
        peer_id = getattr(event, "peer_id", None)
        if ctx.is_peer_allowed(peer_type, peer_id):
            await nxt()
            return
        raise StopPropagation()

    router.use_message(_guard)
    router.use_action(_guard)
    router.use_member_update(_guard)
    router.use_reaction(_guard)
    router.use_deleted_messages(_guard)
    router.use_callback_query(_guard)


async def _load_plugins_once(
    *,
    loader: PluginLoader,
    plugin_paths: list[Path],
) -> None:
    for idx, path in enumerate(plugin_paths):
        if not path.exists():
            raise FileNotFoundError(f"Plugin file not found: {path}")
        await loader.load_path(path, module_name=f"group_bot_plugin_{idx}_{path.stem}")


async def _hydrate_schedules(ctx: GroupBotContext) -> None:
    for ann in ctx.config.announcements:
        ctx.storage.upsert_scheduled_job(
            name=ann.name,
            text=ann.text,
            interval_seconds=ann.every_seconds,
            peer_ref=ann.peer,
            enabled=ann.enabled,
        )
    for job in ctx.storage.list_scheduled_jobs(enabled_only=True):
        await ctx.ensure_schedule(job)


async def main(args: argparse.Namespace) -> None:
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    api_id = int(_need("TELEGRAM_API_ID"))
    api_hash = _need("TELEGRAM_API_HASH")
    runtime, network, session = _resolve_runtime_session(args)

    config_path = Path(args.config).expanduser()
    if not config_path.is_absolute():
        config_path = (Path.cwd() / config_path).resolve()
    cfg = load_group_bot_config(config_path)
    plugin_paths = _resolve_plugin_paths(config_path, cfg.plugin_paths)
    storage = GroupBotStorage(cfg.storage_path)
    scheduler = Scheduler()

    app = Client(
        network=network,
        session_path=session,
        init=ClientInit(api_id=api_id, api_hash=api_hash),
    )
    router = Router()
    loader = PluginLoader(router=router)
    ctx = GroupBotContext(
        app=app,
        router=router,
        scheduler=scheduler,
        storage=storage,
        config=cfg,
        timeout=float(args.timeout),
    )
    attach_group_bot_context(router, ctx)
    _install_scope_middlewares(router, ctx=ctx)
    print(
        f"Using runtime={runtime} network={network} bot_session={session} "
        f"config={config_path}"
    )

    loaded_once = False

    async def _on_startup(_client: Any) -> None:
        nonlocal loaded_once
        resolved = await ctx.resolve_allowed_peer_keys()
        if not loaded_once:
            await _load_plugins_once(loader=loader, plugin_paths=plugin_paths)
            loaded_once = True
        await _hydrate_schedules(ctx)
        await ctx.send_audit(
            "[START] group-bot up "
            f"allowed_peers={sorted(resolved)} read_only_default={cfg.read_only_mode}"
        )

    async def _on_shutdown(_client: Any) -> None:
        await ctx.send_audit("[STOP] group-bot shutting down")
        await scheduler.stop()
        ctx.reset_scheduled_runtime()

    def _make_dispatcher(client: Any, routed: Router) -> Dispatcher:
        return Dispatcher(
            client=client,
            router=routed,
            ignore_outgoing=True,
            ignore_before_start=True,
            backlog_grace_seconds=int(cfg.backlog_grace_seconds),
            backlog_policy=cfg.backlog_policy,
            throttle_global_per_minute=_as_int_or_none(cfg.throttle_global_per_minute),
            throttle_peer_per_minute=_as_int_or_none(cfg.throttle_peer_per_minute),
            throttle_burst=max(1, int(cfg.throttle_burst)),
            throttle_mode=cfg.throttle_mode,
            debug=bool(cfg.debug_dispatcher),
        )

    try:
        await run_userbot(
            client=app.raw,
            router=router,
            make_dispatcher=_make_dispatcher,
            reconnect=ReconnectPolicy(
                enabled=True,
                initial_delay_seconds=1.0,
                max_delay_seconds=30.0,
                multiplier=2.0,
                jitter_ratio=0.2,
            ),
            on_startup=_on_startup,
            on_shutdown=_on_shutdown,
        )
    finally:
        await scheduler.stop()
        storage.close()


if __name__ == "__main__":
    try:
        asyncio.run(main(_parse_args()))
    except KeyboardInterrupt:
        pass
