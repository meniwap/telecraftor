from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from telecraft.client import Client
from telecraft.client.mtproto import ClientInit
from telecraft.client.runtime_isolation import (
    RuntimeIsolationError,
    pick_existing_session,
    require_prod_override,
    resolve_network,
    resolve_report_root,
    resolve_runtime,
    resolve_session_paths,
    validate_session_matches_network,
)

CleanupFn = Callable[[], Any]


def _env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name)
    if v is None or not v.strip():
        return default
    return v.strip()


@dataclass(slots=True)
class LiveConfig:
    api_id: int
    api_hash: str
    runtime: str
    network: str
    session_path: str
    audit_peer_file: Path
    timeout: float
    second_account: str
    audit_peer: str
    report_root: Path
    destructive: bool
    enable_polls: bool
    enable_strict_polls_close: bool
    enable_paid: bool
    enable_premium: bool
    enable_sponsored: bool
    enable_passkeys: bool
    enable_business: bool
    enable_chatlists: bool
    enable_calls: bool
    enable_calls_write: bool
    enable_takeout: bool
    enable_webapps: bool
    enable_admin: bool
    enable_stories_write: bool
    enable_channel_admin: bool


@dataclass(slots=True)
class LiveContext:
    cfg: LiveConfig
    run_id: str
    run_dir: Path
    cleanups: list[CleanupFn] = field(default_factory=list)
    artifacts: dict[str, object] = field(default_factory=dict)

    def add_cleanup(self, fn: CleanupFn) -> None:
        self.cleanups.append(fn)

    async def run_cleanups(self) -> list[str]:
        errors: list[str] = []
        timeout = min(float(self.cfg.timeout), 12.0)
        for fn in reversed(self.cleanups):
            try:
                out = fn()
                if asyncio.iscoroutine(out):
                    await asyncio.wait_for(out, timeout=timeout)
            except Exception as e:  # noqa: BLE001
                errors.append(f"{type(e).__name__}: {e}")
        return errors


def _normalize_second_account(raw: str) -> str:
    s = raw.strip()
    if not s:
        return s
    if s.startswith(("@", "+")):
        return s
    if ":" in s or s.isdigit():
        return s
    # pytest treats leading '@' as a response-file marker, so we accept bare usernames.
    return f"@{s}"


class AuditReporter:
    def __init__(self, ctx: LiveContext) -> None:
        self.ctx = ctx
        self._events_f = (ctx.run_dir / "events.jsonl").open("a", encoding="utf-8")
        self.audit_peer: str | None = None

    def _write_event(self, payload: dict[str, object]) -> None:
        self._events_f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self._events_f.flush()

    async def emit(
        self,
        *,
        client: Client,
        status: str,
        step: str,
        details: str = "",
        to_telegram: bool = True,
    ) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        payload = {
            "ts": ts,
            "run_id": self.ctx.run_id,
            "status": status,
            "step": step,
            "details": details,
        }
        self._write_event(payload)
        if not to_telegram:
            return
        target = self.audit_peer or self.ctx.cfg.audit_peer
        if target == "auto":
            return
        text = f"[{status}] run={self.ctx.run_id} step={step}\n{details}".strip()
        try:
            await client.messages.send(
                target,
                text,
                timeout=min(float(self.ctx.cfg.timeout), 10.0),
            )
        except Exception:  # noqa: BLE001
            # File logs are authoritative; Telegram logging is best-effort.
            return

    async def close(self) -> None:
        self._events_f.close()


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("telecraft-live")
    group.addoption(
        "--run-live",
        action="store_true",
        default=False,
        help="Enable live Telegram tests",
    )
    group.addoption(
        "--live-destructive",
        action="store_true",
        default=False,
        help="Allow destructive live operations (ban/kick/promote/demote/resource create/delete)",
    )
    group.addoption(
        "--live-second-account",
        action="store",
        default="",
        help=(
            "Second account username/phone for cross-account tests "
            "(use bare username, e.g. meniwap)"
        ),
    )
    group.addoption(
        "--live-audit-peer",
        action="store",
        default="auto",
        help="Audit destination peer (@user / channel:ID / auto)",
    )
    group.addoption(
        "--live-report-dir",
        action="store",
        default="reports/live",
        help="Directory for JSONL/Markdown run reports",
    )
    group.addoption(
        "--live-timeout",
        action="store",
        type=float,
        default=45.0,
        help="Default RPC timeout",
    )
    group.addoption(
        "--live-runtime",
        action="store",
        default="sandbox",
        help="Live runtime lane (sandbox/prod). Default: sandbox",
    )
    group.addoption(
        "--allow-prod-live",
        action="store_true",
        default=False,
        help="Allow prod runtime for live tests (requires TELECRAFT_ALLOW_PROD_LIVE=1)",
    )
    group.addoption(
        "--live-network",
        action="store",
        default="",
        help="Deprecated network override (runtime now determines network)",
    )
    group.addoption(
        "--live-enable-polls",
        action="store_true",
        default=False,
        help="Enable live polls/scheduled step (unstable on some schema versions)",
    )
    group.addoption(
        "--live-strict-polls-close",
        action="store_true",
        default=False,
        help="Fail polls live test if poll close fails",
    )
    group.addoption(
        "--live-paid",
        action="store_true",
        default=False,
        help="Enable paid live steps (stars/gifts spending operations)",
    )
    group.addoption(
        "--live-premium",
        action="store_true",
        default=False,
        help="Enable optional premium live lane",
    )
    group.addoption(
        "--live-sponsored",
        action="store_true",
        default=False,
        help="Enable optional sponsored/admin live lane",
    )
    group.addoption(
        "--live-passkeys",
        action="store_true",
        default=False,
        help="Enable optional passkeys live lane",
    )
    group.addoption(
        "--live-business",
        action="store_true",
        default=False,
        help="Enable optional business live lane",
    )
    group.addoption(
        "--live-chatlists",
        action="store_true",
        default=False,
        help="Enable optional chatlists live lane",
    )
    group.addoption(
        "--live-calls",
        action="store_true",
        default=False,
        help="Enable optional calls readonly live lane",
    )
    group.addoption(
        "--live-calls-write",
        action="store_true",
        default=False,
        help="Enable optional calls write/destructive live lane",
    )
    group.addoption(
        "--live-takeout",
        action="store_true",
        default=False,
        help="Enable optional takeout live lane",
    )
    group.addoption(
        "--live-webapps",
        action="store_true",
        default=False,
        help="Enable optional webapps live lane",
    )
    group.addoption(
        "--live-admin",
        action="store_true",
        default=False,
        help="Enable optional admin-sensitive live lane",
    )
    group.addoption(
        "--live-stories-write",
        action="store_true",
        default=False,
        help="Enable optional stories write live lane",
    )
    group.addoption(
        "--live-channel-admin",
        action="store_true",
        default=False,
        help="Enable optional channel admin live lane",
    )
    group.addoption(
        "--live-bot",
        action="store_true",
        default=False,
        help="Enable optional bot-session live lane",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "unit: fast deterministic tests")
    config.addinivalue_line("markers", "live: live tests against Telegram")
    config.addinivalue_line("markers", "destructive: mutating live tests")
    config.addinivalue_line(
        "markers",
        "requires_second_account: live tests requiring second account",
    )
    config.addinivalue_line(
        "markers",
        "requires_business_account: live tests requiring business-enabled account",
    )
    config.addinivalue_line("markers", "live_core: live core lane")
    config.addinivalue_line("markers", "live_second_account: live lane with second account")
    config.addinivalue_line("markers", "live_optional: optional live lane (unstable/expensive)")
    config.addinivalue_line("markers", "live_paid: live lane that may spend Stars")
    config.addinivalue_line("markers", "live_premium: optional premium lane")
    config.addinivalue_line("markers", "live_sponsored: optional sponsored lane")
    config.addinivalue_line("markers", "live_passkeys: optional passkeys lane")
    config.addinivalue_line("markers", "live_business: optional business lane")
    config.addinivalue_line("markers", "live_chatlists: optional chatlists lane")
    config.addinivalue_line("markers", "live_calls: optional calls readonly lane")
    config.addinivalue_line("markers", "live_calls_write: optional calls write lane")
    config.addinivalue_line("markers", "live_takeout: optional takeout lane")
    config.addinivalue_line("markers", "live_webapps: optional webapps lane")
    config.addinivalue_line("markers", "live_admin: optional admin-sensitive lane")
    config.addinivalue_line("markers", "live_stories_write: optional stories write lane")
    config.addinivalue_line("markers", "live_channel_admin: optional channel admin lane")
    config.addinivalue_line("markers", "live_bot: optional bot-session live lane")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--run-live"):
        second_raw = str(config.getoption("--live-second-account")).strip()
        paid_enabled = bool(config.getoption("--live-paid"))
        premium_enabled = bool(config.getoption("--live-premium"))
        sponsored_enabled = bool(config.getoption("--live-sponsored"))
        passkeys_enabled = bool(config.getoption("--live-passkeys"))
        business_enabled = bool(config.getoption("--live-business"))
        chatlists_enabled = bool(config.getoption("--live-chatlists"))
        calls_enabled = bool(config.getoption("--live-calls"))
        calls_write_enabled = bool(config.getoption("--live-calls-write"))
        takeout_enabled = bool(config.getoption("--live-takeout"))
        webapps_enabled = bool(config.getoption("--live-webapps"))
        admin_enabled = bool(config.getoption("--live-admin"))
        stories_write_enabled = bool(config.getoption("--live-stories-write"))
        channel_admin_enabled = bool(config.getoption("--live-channel-admin"))
        bot_enabled = bool(config.getoption("--live-bot"))
        skip_second = pytest.mark.skip(
            reason="Second-account tests require --live-second-account <username>"
        )
        skip_paid = pytest.mark.skip(reason="Paid live tests require --live-paid")
        skip_premium = pytest.mark.skip(reason="Premium live tests require --live-premium")
        skip_sponsored = pytest.mark.skip(reason="Sponsored live tests require --live-sponsored")
        skip_passkeys = pytest.mark.skip(reason="Passkeys live tests require --live-passkeys")
        skip_business = pytest.mark.skip(reason="Business live tests require --live-business")
        skip_chatlists = pytest.mark.skip(reason="Chatlists live tests require --live-chatlists")
        skip_calls = pytest.mark.skip(reason="Calls live tests require --live-calls")
        skip_calls_write = pytest.mark.skip(
            reason="Calls write live tests require --live-calls-write"
        )
        skip_takeout = pytest.mark.skip(reason="Takeout live tests require --live-takeout")
        skip_webapps = pytest.mark.skip(reason="Webapps live tests require --live-webapps")
        skip_admin = pytest.mark.skip(reason="Admin live tests require --live-admin")
        skip_stories_write = pytest.mark.skip(
            reason="Stories write live tests require --live-stories-write"
        )
        skip_channel_admin = pytest.mark.skip(
            reason="Channel admin live tests require --live-channel-admin"
        )
        skip_bot = pytest.mark.skip(reason="Bot live tests require --live-bot")
        for item in items:
            if not second_raw and "requires_second_account" in item.keywords:
                item.add_marker(skip_second)
            if not paid_enabled and "live_paid" in item.keywords:
                item.add_marker(skip_paid)
            if not premium_enabled and "live_premium" in item.keywords:
                item.add_marker(skip_premium)
            if not sponsored_enabled and "live_sponsored" in item.keywords:
                item.add_marker(skip_sponsored)
            if not passkeys_enabled and "live_passkeys" in item.keywords:
                item.add_marker(skip_passkeys)
            if not business_enabled and (
                "live_business" in item.keywords or "requires_business_account" in item.keywords
            ):
                item.add_marker(skip_business)
            if not chatlists_enabled and "live_chatlists" in item.keywords:
                item.add_marker(skip_chatlists)
            if not calls_enabled and "live_calls" in item.keywords:
                item.add_marker(skip_calls)
            if not calls_write_enabled and "live_calls_write" in item.keywords:
                item.add_marker(skip_calls_write)
            if not takeout_enabled and "live_takeout" in item.keywords:
                item.add_marker(skip_takeout)
            if not webapps_enabled and "live_webapps" in item.keywords:
                item.add_marker(skip_webapps)
            if not admin_enabled and "live_admin" in item.keywords:
                item.add_marker(skip_admin)
            if not stories_write_enabled and "live_stories_write" in item.keywords:
                item.add_marker(skip_stories_write)
            if not channel_admin_enabled and "live_channel_admin" in item.keywords:
                item.add_marker(skip_channel_admin)
            if not bot_enabled and "live_bot" in item.keywords:
                item.add_marker(skip_bot)
        return

    skip_live = pytest.mark.skip(reason="Live tests require --run-live")
    skip_second = pytest.mark.skip(reason="Second-account tests require --live-second-account")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)
        if "requires_second_account" in item.keywords:
            item.add_marker(skip_second)


@pytest.fixture
def live_config(pytestconfig: pytest.Config) -> LiveConfig:
    if not pytestconfig.getoption("--run-live"):
        pytest.skip("Live tests require --run-live")

    runtime_raw = str(pytestconfig.getoption("--live-runtime")).strip() or "sandbox"
    network_raw = str(pytestconfig.getoption("--live-network")).strip()
    if network_raw:
        print(
            "Warning: --live-network is deprecated; live runtime determines network. "
            "Use --live-runtime sandbox|prod."
        )
    try:
        runtime = resolve_runtime(runtime_raw, default="sandbox")
        network = resolve_network(runtime=runtime, explicit_network=network_raw or None)
        if runtime == "prod":
            require_prod_override(
                allow_flag=bool(pytestconfig.getoption("--allow-prod-live")),
                env_var="TELECRAFT_ALLOW_PROD_LIVE",
                action="live tests on production Telegram",
                example=(
                    "TELECRAFT_ALLOW_PROD_LIVE=1 ./.venv/bin/python -m pytest "
                    "tests/live/... --run-live --live-runtime prod --allow-prod-live"
                ),
            )
    except RuntimeIsolationError as e:
        raise pytest.UsageError(str(e)) from e

    api_id_raw = _env("TELEGRAM_API_ID")
    api_hash = _env("TELEGRAM_API_HASH")
    if api_id_raw is None or api_hash is None:
        pytest.skip("Missing TELEGRAM_API_ID / TELEGRAM_API_HASH for live tests")
    try:
        api_id = int(api_id_raw)
    except ValueError as e:
        raise pytest.UsageError("TELEGRAM_API_ID must be an int") from e

    session_paths = resolve_session_paths(runtime=runtime, network=network)
    session_path = _env("TELEGRAM_SESSION_PATH")
    if session_path is None:
        session_path = pick_existing_session(session_paths, preferred_dc=2)
    session_path_obj = Path(str(session_path)).expanduser()
    if not session_path_obj.is_absolute():
        session_path_obj = (Path.cwd() / session_path_obj).resolve()
    if not session_path_obj.exists():
        pytest.skip(
            f"No session found for runtime={runtime!r} network={network!r}. Run login first."
        )
    try:
        validate_session_matches_network(
            session_path=session_path_obj,
            expected_network=network,
        )
    except RuntimeIsolationError as e:
        raise pytest.UsageError(str(e)) from e

    report_root_base = Path(str(pytestconfig.getoption("--live-report-dir"))).resolve()
    report_root = resolve_report_root(report_root_base, runtime=runtime).resolve()
    report_root.mkdir(parents=True, exist_ok=True)

    destructive = bool(pytestconfig.getoption("--live-destructive"))
    second_account_raw = str(pytestconfig.getoption("--live-second-account"))
    second_account = _normalize_second_account(second_account_raw)
    print(
        "[telecraft-live] "
        f"runtime={runtime} network={network} "
        f"session={session_path_obj} "
        f"report_root={report_root} "
        f"audit_peer={str(pytestconfig.getoption('--live-audit-peer'))} "
        f"destructive={destructive}",
    )
    return LiveConfig(
        api_id=api_id,
        api_hash=api_hash,
        runtime=runtime,
        network=network,
        session_path=str(session_path_obj),
        audit_peer_file=session_paths.audit_peer_file,
        timeout=float(pytestconfig.getoption("--live-timeout")),
        second_account=second_account,
        audit_peer=str(pytestconfig.getoption("--live-audit-peer")),
        report_root=report_root,
        destructive=destructive,
        enable_polls=bool(pytestconfig.getoption("--live-enable-polls")),
        enable_strict_polls_close=bool(pytestconfig.getoption("--live-strict-polls-close")),
        enable_paid=bool(pytestconfig.getoption("--live-paid")),
        enable_premium=bool(pytestconfig.getoption("--live-premium")),
        enable_sponsored=bool(pytestconfig.getoption("--live-sponsored")),
        enable_passkeys=bool(pytestconfig.getoption("--live-passkeys")),
        enable_business=bool(pytestconfig.getoption("--live-business")),
        enable_chatlists=bool(pytestconfig.getoption("--live-chatlists")),
        enable_calls=bool(pytestconfig.getoption("--live-calls")),
        enable_calls_write=bool(pytestconfig.getoption("--live-calls-write")),
        enable_takeout=bool(pytestconfig.getoption("--live-takeout")),
        enable_webapps=bool(pytestconfig.getoption("--live-webapps")),
        enable_admin=bool(pytestconfig.getoption("--live-admin")),
        enable_stories_write=bool(pytestconfig.getoption("--live-stories-write")),
        enable_channel_admin=bool(pytestconfig.getoption("--live-channel-admin")),
    )


@pytest.fixture
def client_v2(live_config: LiveConfig) -> Client:
    return Client(
        network=live_config.network,
        session_path=live_config.session_path,
        init=ClientInit(api_id=live_config.api_id, api_hash=live_config.api_hash),
    )


@pytest.fixture
def bot_client_v2(live_config: LiveConfig, pytestconfig: pytest.Config) -> Client:
    if not pytestconfig.getoption("--live-bot"):
        pytest.skip("Bot live tests require --live-bot")

    session_paths = resolve_session_paths(
        runtime=live_config.runtime,
        network=live_config.network,
    )
    bot_session = _env("TELEGRAM_BOT_SESSION_PATH")
    if bot_session is None:
        bot_session = pick_existing_session(
            session_paths,
            preferred_dc=2,
            kind="bot",
        )
    bot_session_obj = Path(str(bot_session)).expanduser()
    if not bot_session_obj.is_absolute():
        bot_session_obj = (Path.cwd() / bot_session_obj).resolve()
    if not bot_session_obj.exists():
        pytest.skip(
            "No bot session found for bot lane. "
            "Run login-bot first or set TELEGRAM_BOT_SESSION_PATH."
        )
    try:
        validate_session_matches_network(
            session_path=bot_session_obj,
            expected_network=live_config.network,
        )
    except RuntimeIsolationError as e:
        raise pytest.UsageError(str(e)) from e

    return Client(
        network=live_config.network,
        session_path=str(bot_session_obj),
        init=ClientInit(api_id=live_config.api_id, api_hash=live_config.api_hash),
    )


@pytest.fixture
def live_context(live_config: LiveConfig) -> LiveContext:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    run_dir = (live_config.report_root / run_id).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    return LiveContext(cfg=live_config, run_id=run_id, run_dir=run_dir)


@pytest.fixture
def audit_reporter(live_context: LiveContext) -> AuditReporter:
    return AuditReporter(live_context)
