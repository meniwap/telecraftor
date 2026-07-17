from __future__ import annotations

import argparse
import asyncio
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


def test_run_runtime_cli__defaults_to_prod_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = _load_run_module()
    monkeypatch.setenv("TELECRAFT_ALLOW_PROD", "1")
    args = argparse.Namespace(cmd="me", runtime="prod", network=None, allow_prod=True)
    runtime, network = run._resolve_runtime_network(args)
    assert runtime == "prod"
    assert network == "prod"


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


def test_run_runtime_cli__rejects_sandbox_runtime() -> None:
    run = _load_run_module()
    args = argparse.Namespace(cmd="me", runtime="sandbox", network=None, allow_prod=False)
    with pytest.raises(SystemExit):
        run._resolve_runtime_network(args)


def test_run_runtime_cli__resolve_runtime_context__defaults_to_user_session_kind(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run = _load_run_module()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TELECRAFT_ALLOW_PROD", "1")
    args = argparse.Namespace(
        cmd="me",
        runtime="prod",
        network=None,
        allow_prod=True,
        session=None,
        dc=2,
        session_kind="user",
    )
    ctx = run._resolve_runtime_context(args, allow_missing_session=True)
    assert ctx.session_kind == "user"
    assert ctx.session_path.endswith("prod_dc2.session.json")


def test_run_runtime_cli__resolve_runtime_context__supports_bot_session_kind(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run = _load_run_module()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TELECRAFT_ALLOW_PROD", "1")
    args = argparse.Namespace(
        cmd="me",
        runtime="prod",
        network=None,
        allow_prod=True,
        session=None,
        dc=2,
        session_kind="bot",
    )
    ctx = run._resolve_runtime_context(args, allow_missing_session=True)
    assert ctx.session_kind == "bot"
    assert ctx.session_path.endswith("prod_dc2.bot.session.json")


def test_run_runtime_cli__keepalive_pings_while_waiting() -> None:
    run = _load_run_module()

    class FakeClient:
        def __init__(self) -> None:
            self.pings = 0

        async def ping(self, *, timeout: float = 20.0) -> object:
            _ = timeout
            self.pings += 1
            return object()

    async def _exercise() -> FakeClient:
        client = FakeClient()
        stop = asyncio.Event()
        task = asyncio.create_task(
            run._keepalive_while_waiting(client, stop, interval=0.01, timeout=0.01)
        )
        await asyncio.sleep(0.035)
        stop.set()
        await task
        return client

    client = asyncio.run(_exercise())
    assert client.pings >= 1


def test_run_runtime_cli__uses_hidden_prompt_for_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = _load_run_module()
    prompts: list[str] = []

    def _hidden(prompt: str) -> str:
        prompts.append(prompt)
        return " secret-value "

    async def _visible(_prompt: str) -> str:
        raise AssertionError("visible input must not be used for a secret")

    class FakeClient:
        async def ping(self, *, timeout: float = 20.0) -> object:
            _ = timeout
            return object()

    monkeypatch.setattr(run.getpass, "getpass", _hidden)
    monkeypatch.setattr(run, "_prompt_input", _visible)
    value = asyncio.run(
        run._prompt_with_keepalive(
            FakeClient(),
            "2FA password: ",
            timeout=1.0,
            secret=True,
        )
    )
    assert value == " secret-value "
    assert prompts == ["2FA password: "]
