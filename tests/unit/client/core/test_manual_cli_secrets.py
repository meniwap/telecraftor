from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
MANUAL_TOOLS = (
    ROOT / "tools" / "manual" / "smoke_login.py",
    ROOT / "tools" / "manual" / "smoke_get_me.py",
    ROOT / "tools" / "manual" / "smoke_updates.py",
)
SECRET_ARGUMENTS = ("--api-hash", "--bot-token", "--code", "--password", "--phone")


def test_manual_cli__credentials_and_phone_are_not_accepted_via_argv() -> None:
    for path in MANUAL_TOOLS:
        result = subprocess.run(
            [sys.executable, str(path), "--help"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        for option in SECRET_ARGUMENTS:
            assert option not in result.stdout, f"{path.name} exposes {option}"
