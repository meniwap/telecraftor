from __future__ import annotations

import re
from pathlib import Path

import telecraft

PYPROJECT_PATH = Path("pyproject.toml")
PROJECT_VERSION_RE = re.compile(r'(?m)^version\s*=\s*"([^"]+)"$')


def _project_version() -> str:
    raw = PYPROJECT_PATH.read_text(encoding="utf-8")
    match = PROJECT_VERSION_RE.search(raw)
    if match is None:
        raise AssertionError("Could not locate [project].version in pyproject.toml")
    return match.group(1)


def test_project_version_matches_package_version() -> None:
    assert _project_version() == telecraft.__version__
