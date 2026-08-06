from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


def _load_live_conftest_module():
    path = Path("tests/live/conftest.py")
    spec = importlib.util.spec_from_file_location("telecraft_tests_live_conftest", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


class _DummyConfig:
    def __init__(self, overrides: dict[str, object] | None = None) -> None:
        self._options: dict[str, object] = {
            "--run-live": False,
            "--live-profile": "prod_safe",
            "--allow-destructive-live": False,
            "--live-destructive-peer": "",
            "--live-audit-peer": "auto",
        }
        if overrides:
            self._options.update(overrides)

    def getoption(self, name: str):
        return self._options[name]


class _DummyItem:
    def __init__(self, *keywords: str) -> None:
        self.keywords = {k: True for k in keywords}
        self.added_markers: list[object] = []

    def add_marker(self, marker: object) -> None:
        self.added_markers.append(marker)


def _skip_reasons(item: _DummyItem) -> list[str]:
    reasons: list[str] = []
    for marker in item.added_markers:
        mark = getattr(marker, "mark", None)
        if mark is None or getattr(mark, "name", "") != "skip":
            continue
        reason = mark.kwargs.get("reason")
        if isinstance(reason, str):
            reasons.append(reason)
    return reasons


def test_live_config__skips_live_tests_unless_enabled() -> None:
    mod = _load_live_conftest_module()
    cfg = _DummyConfig()
    item = _DummyItem("live", "live_prod_safe")

    mod.pytest_collection_modifyitems(cfg, [item])

    assert "Live tests require --run-live" in _skip_reasons(item)


def test_live_config__preserves_live_tests_when_enabled() -> None:
    mod = _load_live_conftest_module()
    cfg = _DummyConfig({"--run-live": True})
    item = _DummyItem("live", "live_prod_safe")

    mod.pytest_collection_modifyitems(cfg, [item])

    assert not _skip_reasons(item)


def test_live_config__prod_safe_skips_destructive_tests() -> None:
    mod = _load_live_conftest_module()
    cfg = _DummyConfig({"--run-live": True})
    item = _DummyItem("live", "live_destructive")

    mod.pytest_collection_modifyitems(cfg, [item])

    assert any("Destructive live tests require" in reason for reason in _skip_reasons(item))


def test_live_config__destructive_profile_requires_gates_and_selects_only_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _load_live_conftest_module()
    cfg = _DummyConfig(
        {
            "--run-live": True,
            "--live-profile": "destructive_message",
            "--allow-destructive-live": True,
            "--live-destructive-peer": "approvedpeer",
        }
    )
    destructive_item = _DummyItem("live", "live_destructive")
    readonly_item = _DummyItem("live", "live_prod_safe")

    with pytest.raises(pytest.UsageError, match="TELECRAFT_ALLOW_DESTRUCTIVE_LIVE=1"):
        mod.pytest_collection_modifyitems(cfg, [destructive_item, readonly_item])

    monkeypatch.setenv("TELECRAFT_ALLOW_DESTRUCTIVE_LIVE", "1")
    monkeypatch.setenv("TELECRAFT_DESTRUCTIVE_PEER", "@ApprovedPeer")
    mod.pytest_collection_modifyitems(cfg, [destructive_item, readonly_item])

    assert not _skip_reasons(destructive_item)
    assert any("runs only live_destructive" in reason for reason in _skip_reasons(readonly_item))


def test_live_config__rejects_unknown_live_profile() -> None:
    mod = _load_live_conftest_module()
    cfg = _DummyConfig({"--live-profile": "experimental"})

    with pytest.raises(pytest.UsageError, match="Unsupported --live-profile"):
        mod.pytest_collection_modifyitems(cfg, [])


def _synthetic_live_config(mod, tmp_path: Path):
    return mod.LiveConfig(
        api_id=987654321,
        api_hash="synthetic-api-hash",
        runtime="prod",
        live_profile="prod_safe",
        network="prod",
        session_path="synthetic.session.json",
        timeout=1.0,
        audit_peer="auto",
        report_root=tmp_path,
    )


def test_live_config__repr_omits_api_credentials(tmp_path: Path) -> None:
    mod = _load_live_conftest_module()
    cfg = _synthetic_live_config(mod, tmp_path)

    rendered = repr(cfg)

    assert str(cfg.api_id) not in rendered
    assert cfg.api_hash not in rendered
    assert "api_id=" not in rendered
    assert "api_hash=" not in rendered


def test_audit_reporter__redacts_api_credentials_from_event_details(tmp_path: Path) -> None:
    mod = _load_live_conftest_module()
    cfg = _synthetic_live_config(mod, tmp_path)
    ctx = mod.LiveContext(
        cfg=cfg,
        run_id="synthetic-run",
        run_dir=tmp_path,
        source_commit="a" * 40,
        source_tree_clean=True,
    )
    reporter = mod.AuditReporter(ctx)

    asyncio.run(
        reporter.emit(
            client=object(),
            status="FAIL",
            step="synthetic",
            details=f"api_id={cfg.api_id} api_hash={cfg.api_hash}",
            to_telegram=False,
        )
    )
    asyncio.run(reporter.close())

    event = json.loads((tmp_path / "events.jsonl").read_text(encoding="utf-8"))
    rendered = json.dumps(event)
    assert str(cfg.api_id) not in rendered
    assert cfg.api_hash not in rendered
    assert event["details"] == "api_id=<redacted> api_hash=<redacted>"


@pytest.mark.parametrize("live_profile", ["prod_safe", "destructive_message"])
def test_audit_reporter__protected_profiles_never_write_to_telegram(
    tmp_path: Path,
    live_profile: str,
) -> None:
    mod = _load_live_conftest_module()
    cfg = _synthetic_live_config(mod, tmp_path)
    cfg.live_profile = live_profile
    cfg.audit_peer = "approvedpeer"
    ctx = mod.LiveContext(
        cfg=cfg,
        run_id="synthetic-run",
        run_dir=tmp_path,
        source_commit="a" * 40,
        source_tree_clean=True,
    )
    reporter = mod.AuditReporter(ctx)
    calls: list[tuple[object, str]] = []

    async def _send(peer: object, text: str, **_kwargs: object) -> None:
        calls.append((peer, text))

    client = SimpleNamespace(messages=SimpleNamespace(send=_send))
    asyncio.run(
        reporter.emit(
            client=client,
            status="PASS",
            step="synthetic",
            details="protected",
            to_telegram=True,
        )
    )
    asyncio.run(reporter.close())

    assert calls == []


def test_live_context__destructive_cleanup_gets_extended_total_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _load_live_conftest_module()
    cfg = _synthetic_live_config(mod, tmp_path)
    cfg.live_profile = "destructive_message"
    ctx = mod.LiveContext(
        cfg=cfg,
        run_id="synthetic-run",
        run_dir=tmp_path,
        source_commit="a" * 40,
        source_tree_clean=True,
    )
    observed_timeouts: list[float] = []
    original_wait_for = mod.asyncio.wait_for

    async def _capturing_wait_for(awaitable: object, *, timeout: float):
        observed_timeouts.append(timeout)
        return await original_wait_for(awaitable, timeout=timeout)

    monkeypatch.setattr(mod.asyncio, "wait_for", _capturing_wait_for)

    async def _cleanup() -> None:
        return None

    ctx.add_cleanup(_cleanup)
    assert asyncio.run(ctx.run_cleanups()) == []
    assert observed_timeouts == [40.0]
