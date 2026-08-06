from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _run_help(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args, "--help"],
        cwd=Path(__file__).resolve().parents[4],
        check=False,
        capture_output=True,
        text=True,
    )


def test_public_cli__package_module__exposes_login_help() -> None:
    result = _run_help("-m", "telecraft.cli")

    assert result.returncode == 0, result.stderr
    assert "login" in result.stdout
    assert "login-bot" in result.stdout


def test_public_cli__apps_wrapper__preserves_legacy_command() -> None:
    result = _run_help("apps/run.py")

    assert result.returncode == 0, result.stderr
    assert "login" in result.stdout


def test_public_cli__login_help__does_not_accept_secrets_on_command_line() -> None:
    login = _run_help("-m", "telecraft.cli", "login")
    login_bot = _run_help("-m", "telecraft.cli", "login-bot")

    assert login.returncode == 0, login.stderr
    assert login_bot.returncode == 0, login_bot.stderr
    assert "--code" not in login.stdout
    assert "--password" not in login.stdout
    assert "--phone" not in login.stdout
    assert "--bot-token" not in login_bot.stdout
