from __future__ import annotations

import re
from pathlib import Path

import telecraft

PYPROJECT_PATH = Path("pyproject.toml")
README_PATH = Path("README.md")
CHANGELOG_PATH = Path("CHANGELOG.md")
RELEASE_WORKFLOW_PATHS = (
    Path(".github/workflows/ci.yml"),
    Path(".github/workflows/publish.yml"),
    Path(".github/workflows/testpypi.yml"),
)
PROJECT_VERSION_RE = re.compile(r'(?m)^version\s*=\s*"([^"]+)"$')


def _project_version() -> str:
    raw = PYPROJECT_PATH.read_text(encoding="utf-8")
    match = PROJECT_VERSION_RE.search(raw)
    if match is None:
        raise AssertionError("Could not locate [project].version in pyproject.toml")
    return match.group(1)


def test_project_version_matches_package_version() -> None:
    assert _project_version() == telecraft.__version__


def test_release_dependency_floors_are_pinned_in_project_metadata() -> None:
    raw = PYPROJECT_PATH.read_text(encoding="utf-8")

    assert 'requires = ["hatchling>=1.26.3"]' in raw
    assert '"cryptography>=50.0.0"' in raw
    assert '"pip-audit>=2.10"' in raw
    assert "fail_under = 70" in raw


def test_release_workflows_enforce_quality_gates() -> None:
    workflows = {path: path.read_text(encoding="utf-8") for path in RELEASE_WORKFLOW_PATHS}

    for path, raw in workflows.items():
        assert "python tools/check_repo_hygiene.py --history" in raw, path
        assert "python -m ruff format --check" in raw, path
        assert "python -m pip_audit --strict ." in raw, path
        assert "--cov=telecraft" in raw, path

    ci = workflows[Path(".github/workflows/ci.yml")]
    assert '"hatchling==1.26.3"' in ci
    assert '"cryptography==50.0.0"' in ci


def test_stable_release_version_is_explicit() -> None:
    version = _project_version()
    readme = README_PATH.read_text(encoding="utf-8")
    changelog = CHANGELOG_PATH.read_text(encoding="utf-8")

    assert f"Current stable version: `{version}`." in readme
    assert f"Current development version: `{version}` (unreleased)." not in readme
    assert f"@v{version}" in readme
    assert f"## [{version}] - Unreleased" not in changelog
    assert re.search(rf"(?m)^## \[{re.escape(version)}\] - \d{{4}}-\d{{2}}-\d{{2}}$", changelog)
