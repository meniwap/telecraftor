from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

import pytest


def _load_run_module():
    path = Path("apps/run.py")
    spec = importlib.util.spec_from_file_location("telecraft_apps_run", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_run_runtime_cli__defaults_to_sandbox_network() -> None:
    run = _load_run_module()
    args = argparse.Namespace(cmd="me", runtime="sandbox", network=None, allow_prod=False)
    runtime, network = run._resolve_runtime_network(args)
    assert runtime == "sandbox"
    assert network == "test"


def test_run_runtime_cli__blocks_prod_without_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = _load_run_module()
    monkeypatch.delenv("TELECRAFT_ALLOW_PROD", raising=False)
    args = argparse.Namespace(cmd="me", runtime="prod", network=None, allow_prod=False)
    with pytest.raises(SystemExit):
        run._resolve_runtime_network(args)


def test_run_runtime_cli__allows_prod_with_flag_and_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = _load_run_module()
    monkeypatch.setenv("TELECRAFT_ALLOW_PROD", "1")
    args = argparse.Namespace(cmd="me", runtime="prod", network=None, allow_prod=True)
    runtime, network = run._resolve_runtime_network(args)
    assert runtime == "prod"
    assert network == "prod"


def test_run_runtime_cli__rejects_network_mismatch() -> None:
    run = _load_run_module()
    args = argparse.Namespace(cmd="me", runtime="sandbox", network="prod", allow_prod=False)
    with pytest.raises(SystemExit):
        run._resolve_runtime_network(args)
