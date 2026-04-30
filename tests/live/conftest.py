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
    live_profile: str
    network: str
    session_path: str
    timeout: float
    audit_peer: str
    report_root: Path


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


def _resolve_live_profile(raw: str) -> str:
    value = (raw or "default").strip().lower() or "default"
    if value in {"default", "prod_safe"}:
        return value
    raise ValueError(f"Unsupported --live-profile {raw!r}; expected 'default' or 'prod_safe'")


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
        ts = datetime.now(timezone.utc).isoformat()
        payload = {
            "ts": ts,
            "run_id": self.ctx.run_id,
            "status": status,
            "step": step,
            "details": details,
        }
        if error_class is not None:
            payload["error_class"] = error_class
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
        help="Live execution profile (default/prod_safe). Default: default",
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


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    try:
        live_profile = _resolve_live_profile(str(config.getoption("--live-profile")))
    except ValueError as e:
        raise pytest.UsageError(str(e)) from e

    if config.getoption("--run-live"):
        if live_profile != "prod_safe":
            print(
                "[telecraft-live] Warning: --live-profile prod_safe is recommended for "
                "production smoke runs."
            )
        return

    skip_live = pytest.mark.skip(reason="Live tests require --run-live")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)


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
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    run_dir = (live_config.report_root / run_id).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    return LiveContext(cfg=live_config, run_id=run_id, run_dir=run_dir)


@pytest.fixture
def audit_reporter(live_context: LiveContext) -> AuditReporter:
    return AuditReporter(live_context)
