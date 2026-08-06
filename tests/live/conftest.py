from __future__ import annotations

import asyncio
import json
import os
import subprocess
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
from tests.live._destructive_message import (
    DESTRUCTIVE_MESSAGE_PROFILE,
    DestructiveLiveGateError,
    resolve_destructive_message_gate,
)

CleanupFn = Callable[[], Any]


def _env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name)
    if v is None or not v.strip():
        return default
    return v.strip()


@dataclass(slots=True)
class LiveConfig:
    api_id: int = field(repr=False)
    api_hash: str = field(repr=False)
    runtime: str
    live_profile: str
    network: str
    session_path: str
    timeout: float
    audit_peer: str
    report_root: Path
    destructive_peer: str | None = None

    def redact(self, value: object) -> str:
        text = str(value)
        credentials = sorted(
            {credential for credential in (self.api_hash, str(self.api_id)) if credential},
            key=len,
            reverse=True,
        )
        for credential in credentials:
            text = text.replace(credential, "<redacted>")
        return text


@dataclass(slots=True)
class LiveContext:
    cfg: LiveConfig
    run_id: str
    run_dir: Path
    source_commit: str
    source_tree_clean: bool
    cleanups: list[CleanupFn] = field(default_factory=list)
    artifacts: dict[str, object] = field(default_factory=dict)

    def add_cleanup(self, fn: CleanupFn) -> None:
        self.cleanups.append(fn)

    def redact(self, value: object) -> str:
        return self.cfg.redact(value)

    async def run_cleanups(self) -> list[str]:
        errors: list[str] = []
        timeout = (
            40.0
            if self.cfg.live_profile == DESTRUCTIVE_MESSAGE_PROFILE
            else min(float(self.cfg.timeout), 12.0)
        )
        for fn in reversed(self.cleanups):
            try:
                out = fn()
                if asyncio.iscoroutine(out):
                    await asyncio.wait_for(out, timeout=timeout)
            except Exception as e:  # noqa: BLE001
                errors.append(self.redact(f"{type(e).__name__}: {e}"))
        return errors


def _resolve_live_profile(raw: str) -> str:
    value = (raw or "default").strip().lower() or "default"
    if value in {"default", "prod_safe", DESTRUCTIVE_MESSAGE_PROFILE}:
        return value
    raise ValueError(
        f"Unsupported --live-profile {raw!r}; expected 'default', 'prod_safe', "
        f"or {DESTRUCTIVE_MESSAGE_PROFILE!r}"
    )


def _source_snapshot() -> tuple[str, bool]:
    root = Path(__file__).resolve().parents[2]
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise pytest.UsageError("Live evidence requires a readable Git source checkout") from exc
    if len(commit) != 40:
        raise pytest.UsageError("Live evidence requires a full Git commit SHA")
    return commit, not bool(status.strip())


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
        error_class: str | None = None,
        to_telegram: bool = True,
    ) -> None:
        status = self.ctx.redact(status)
        step = self.ctx.redact(step)
        details = self.ctx.redact(details)
        if error_class is not None:
            error_class = self.ctx.redact(error_class)
        ts = datetime.now(timezone.utc).isoformat()
        payload: dict[str, object] = {
            "ts": ts,
            "run_id": self.ctx.redact(self.ctx.run_id),
            "status": status,
            "step": step,
            "details": details,
        }
        if error_class is not None:
            payload["error_class"] = error_class
        self._write_event(payload)
        if not to_telegram:
            return

        if self.ctx.cfg.live_profile in {"prod_safe", DESTRUCTIVE_MESSAGE_PROFILE}:
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
        "--allow-prod-live",
        action="store_true",
        default=False,
        help="Allow prod runtime for live tests (requires TELECRAFT_ALLOW_PROD_LIVE=1)",
    )
    group.addoption(
        "--live-profile",
        action="store",
        default="default",
        help=("Live execution profile (default/prod_safe/destructive_message). Default: default"),
    )
    group.addoption(
        "--allow-destructive-live",
        action="store_true",
        default=False,
        help=(
            "Allow the destructive message round-trip (also requires "
            "TELECRAFT_ALLOW_DESTRUCTIVE_LIVE=1)"
        ),
    )
    group.addoption(
        "--live-destructive-peer",
        action="store",
        default="",
        help="Explicit peer for the destructive message round-trip",
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
        "--live-audit-peer",
        action="store",
        default="auto",
        help="Optional audit destination peer (@user/channel:ID). 'auto' writes file reports only.",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "unit: fast deterministic tests")
    config.addinivalue_line("markers", "live: live tests against Telegram")
    config.addinivalue_line("markers", "live_prod_safe: prod-safe live smoke tests")
    config.addinivalue_line(
        "markers",
        "live_destructive: explicitly gated live tests that create and clean up resources",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    try:
        live_profile = _resolve_live_profile(str(config.getoption("--live-profile")))
    except ValueError as e:
        raise pytest.UsageError(str(e)) from e

    if not config.getoption("--run-live"):
        skip_live = pytest.mark.skip(reason="Live tests require --run-live")
        for item in items:
            if "live" in item.keywords:
                item.add_marker(skip_live)
        return

    if live_profile == DESTRUCTIVE_MESSAGE_PROFILE:
        try:
            resolve_destructive_message_gate(
                live_profile=live_profile,
                allow_flag=bool(config.getoption("--allow-destructive-live")),
                env_allow=_env("TELECRAFT_ALLOW_DESTRUCTIVE_LIVE"),
                cli_peer=str(config.getoption("--live-destructive-peer")),
                env_peer=_env("TELECRAFT_DESTRUCTIVE_PEER"),
                audit_peer=str(config.getoption("--live-audit-peer")),
            )
        except DestructiveLiveGateError as e:
            raise pytest.UsageError(str(e)) from e
        skip_other_live = pytest.mark.skip(
            reason="destructive_message profile runs only live_destructive tests"
        )
        for item in items:
            if "live" in item.keywords and "live_destructive" not in item.keywords:
                item.add_marker(skip_other_live)
        return

    skip_destructive = pytest.mark.skip(
        reason="Destructive live tests require --live-profile destructive_message"
    )
    skip_non_prod_safe = pytest.mark.skip(reason="prod_safe profile runs only live_prod_safe tests")
    for item in items:
        if "live_destructive" in item.keywords:
            item.add_marker(skip_destructive)
        elif (
            live_profile == "prod_safe"
            and "live" in item.keywords
            and "live_prod_safe" not in item.keywords
        ):
            item.add_marker(skip_non_prod_safe)

    if live_profile != "prod_safe":
        print(
            "[telecraft-live] Warning: --live-profile prod_safe is recommended for "
            "production smoke runs."
        )


@pytest.fixture
def live_config(pytestconfig: pytest.Config) -> LiveConfig:
    if not pytestconfig.getoption("--run-live"):
        pytest.skip("Live tests require --run-live")

    try:
        live_profile = _resolve_live_profile(str(pytestconfig.getoption("--live-profile")))
        runtime = resolve_runtime("prod", default="prod")
        network = resolve_network(runtime=runtime, explicit_network=None)
        require_prod_override(
            allow_flag=bool(pytestconfig.getoption("--allow-prod-live")),
            env_var="TELECRAFT_ALLOW_PROD_LIVE",
            action="live tests on production Telegram",
            example=(
                "TELECRAFT_ALLOW_PROD_LIVE=1 ./.venv/bin/python -m pytest "
                "tests/live --run-live --allow-prod-live --live-profile prod_safe"
            ),
        )
    except RuntimeIsolationError as e:
        raise pytest.UsageError(str(e)) from e
    except ValueError as e:
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
    audit_peer = str(pytestconfig.getoption("--live-audit-peer")).strip() or "auto"
    destructive_peer: str | None = None
    if live_profile == DESTRUCTIVE_MESSAGE_PROFILE:
        try:
            destructive_peer = resolve_destructive_message_gate(
                live_profile=live_profile,
                allow_flag=bool(pytestconfig.getoption("--allow-destructive-live")),
                env_allow=_env("TELECRAFT_ALLOW_DESTRUCTIVE_LIVE"),
                cli_peer=str(pytestconfig.getoption("--live-destructive-peer")),
                env_peer=_env("TELECRAFT_DESTRUCTIVE_PEER"),
                audit_peer=audit_peer,
            )
        except DestructiveLiveGateError as e:
            raise pytest.UsageError(str(e)) from e
    elif live_profile == "prod_safe":
        audit_peer = "auto"
    print(
        "[telecraft-live] "
        f"runtime={runtime} profile={live_profile} network={network} "
        f"session={session_path_obj} report_root={report_root} audit_peer={audit_peer}",
    )
    return LiveConfig(
        api_id=api_id,
        api_hash=api_hash,
        runtime=runtime,
        live_profile=live_profile,
        network=network,
        session_path=str(session_path_obj),
        timeout=float(pytestconfig.getoption("--live-timeout")),
        audit_peer=audit_peer,
        report_root=report_root,
        destructive_peer=destructive_peer,
    )


@pytest.fixture
def client_v2(live_config: LiveConfig) -> Client:
    return Client(
        network=live_config.network,
        session_path=live_config.session_path,
        init=ClientInit(api_id=live_config.api_id, api_hash=live_config.api_hash),
    )


@pytest.fixture
def live_context(live_config: LiveConfig) -> LiveContext:
    source_commit, source_tree_clean = _source_snapshot()
    if (
        live_config.live_profile in {"prod_safe", DESTRUCTIVE_MESSAGE_PROFILE}
        and not source_tree_clean
    ):
        raise pytest.UsageError(
            f"{live_config.live_profile} live evidence requires a clean source tree before "
            "the run starts"
        )
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    run_dir = (live_config.report_root / run_id).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    return LiveContext(
        cfg=live_config,
        run_id=run_id,
        run_dir=run_dir,
        source_commit=source_commit,
        source_tree_clean=source_tree_clean,
    )


@pytest.fixture
def audit_reporter(live_context: LiveContext) -> AuditReporter:
    return AuditReporter(live_context)
