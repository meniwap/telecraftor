from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


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
            "--run-live": True,
            "--live-runtime": "prod",
            "--live-profile": "prod_safe",
            "--live-second-account": "",
            "--live-paid": False,
            "--live-premium": False,
            "--live-sponsored": False,
            "--live-passkeys": False,
            "--live-business": False,
            "--live-chatlists": False,
            "--live-calls": False,
            "--live-calls-write": False,
            "--live-takeout": False,
            "--live-webapps": False,
            "--live-admin": False,
            "--live-stories-write": False,
            "--live-channel-admin": False,
            "--live-bot": False,
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


def test_live_config__prod_safe_profile__skips_destructive_marked_tests() -> None:
    mod = _load_live_conftest_module()
    cfg = _DummyConfig()
    items = [
        _DummyItem("live", "live_core", "destructive", "live_core_destructive"),
        _DummyItem("live", "live_optional", "destructive"),
    ]

    mod.pytest_collection_modifyitems(cfg, items)

    for item in items:
        reasons = _skip_reasons(item)
        assert any("prod_safe policy" in r for r in reasons)


def test_live_config__prod_safe_profile__skips_second_account_and_paid_and_admin_lanes() -> None:
    mod = _load_live_conftest_module()
    cfg = _DummyConfig()
    items = [
        _DummyItem("live", "requires_second_account", "live_second_account"),
        _DummyItem("live", "live_optional", "live_paid"),
        _DummyItem("live", "live_optional", "live_admin"),
        _DummyItem("live", "live_optional", "live_calls_write"),
    ]

    mod.pytest_collection_modifyitems(cfg, items)

    for item in items:
        reasons = _skip_reasons(item)
        assert any("prod_safe policy" in r for r in reasons)


def test_live_config__prod_safe_profile__preserves_core_safe_and_prod_safe_baseline_tests() -> None:
    mod = _load_live_conftest_module()
    cfg = _DummyConfig({"--live-calls": True})
    items = [
        _DummyItem("live", "live_core", "live_core_safe"),
        _DummyItem("live", "live_optional", "live_prod_safe"),
    ]

    mod.pytest_collection_modifyitems(cfg, items)

    for item in items:
        reasons = _skip_reasons(item)
        assert not any("prod_safe policy" in r for r in reasons)
