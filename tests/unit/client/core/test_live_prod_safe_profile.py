from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

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


def test_live_config__rejects_unknown_live_profile() -> None:
    mod = _load_live_conftest_module()
    cfg = _DummyConfig({"--live-profile": "experimental"})

    with pytest.raises(pytest.UsageError, match="Unsupported --live-profile"):
        mod.pytest_collection_modifyitems(cfg, [])
