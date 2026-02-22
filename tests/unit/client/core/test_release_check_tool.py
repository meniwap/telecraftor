from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _load_release_check_module():
    path = Path("tools/release_check.py")
    spec = importlib.util.spec_from_file_location("telecraft_tools_release_check", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _write_file(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")


def _create_repo(
    root: Path,
    *,
    version: str = "0.2.0b1",
    changelog_version: str | None = None,
) -> None:
    changelog_version = version if changelog_version is None else changelog_version
    _write_file(
        root / "pyproject.toml",
        f"[project]\nname = \"telecraft\"\nversion = \"{version}\"\n",
    )
    _write_file(
        root / "CHANGELOG.md",
        (
            "# Changelog\n\n## [Unreleased]\n\n"
            f"## [{changelog_version}] - 2026-02-22\n\n- Test entry.\n"
        ),
    )
    _write_json(
        root / "tests/meta/v2_support_contract.json",
        {
            "version": 1,
            "defaults": {
                "stable": {
                    "support_tier": "B",
                    "compat": "additive+deprecation",
                    "live_gate": "none",
                },
                "experimental": {
                    "support_tier": "experimental",
                    "compat": "best_effort",
                    "live_gate": "none",
                },
            },
            "namespace_overrides": {},
            "method_overrides": {},
        },
    )
    _write_json(root / "tests/meta/v2_deprecations.json", {"version": 1, "deprecations": []})


def _create_prod_safe_run(root: Path, run_id: str, *, fail_count: int = 0) -> None:
    run_dir = root / "reports/live/prod" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_file(run_dir / "events.jsonl", "{}\n")
    _write_file(run_dir / "summary.md", "# Summary\n")
    _write_json(
        run_dir / "artifacts.json",
        {
            "run_id": run_id,
            "fail_count": fail_count,
            "connection_health_probes": {
                "enabled": True,
                "probe": "profile.me",
                "pass": 1,
                "fail": 0,
            },
        },
    )


def test_release_check__fails_on_version_changelog_mismatch(tmp_path: Path) -> None:
    mod = _load_release_check_module()
    _create_repo(tmp_path, version="0.2.0b1", changelog_version="0.2.0b2")
    _create_prod_safe_run(tmp_path, "core")
    _create_prod_safe_run(tmp_path, "base")

    rc = mod.run(
        [
            "--version",
            "0.2.0b1",
            "--release-type",
            "beta",
            "--prod-safe-run-core",
            "core",
            "--prod-safe-run-baseline",
            "base",
            "--write-dir",
            str(tmp_path / "out"),
            "--dry-run",
        ],
        root=tmp_path,
    )
    assert rc == 1


def test_release_check__fails_when_prod_safe_artifacts_missing(tmp_path: Path) -> None:
    mod = _load_release_check_module()
    _create_repo(tmp_path)
    _create_prod_safe_run(tmp_path, "core")

    rc = mod.run(
        [
            "--version",
            "0.2.0b1",
            "--release-type",
            "beta",
            "--prod-safe-run-core",
            "core",
            "--prod-safe-run-baseline",
            "base",
            "--write-dir",
            str(tmp_path / "out"),
            "--dry-run",
        ],
        root=tmp_path,
    )
    assert rc == 1


def test_release_check__fails_when_artifacts_report_failures(tmp_path: Path) -> None:
    mod = _load_release_check_module()
    _create_repo(tmp_path)
    _create_prod_safe_run(tmp_path, "core", fail_count=1)
    _create_prod_safe_run(tmp_path, "base")

    rc = mod.run(
        [
            "--version",
            "0.2.0b1",
            "--release-type",
            "beta",
            "--prod-safe-run-core",
            "core",
            "--prod-safe-run-baseline",
            "base",
            "--write-dir",
            str(tmp_path / "out"),
            "--dry-run",
        ],
        root=tmp_path,
    )
    assert rc == 1


def test_release_check__accepts_alpha_beta_rc_versions() -> None:
    mod = _load_release_check_module()

    mod.validate_release_type_for_version(mod.parse_version("0.2.0a1"), "alpha")
    mod.validate_release_type_for_version(mod.parse_version("0.2.0b1"), "beta")
    mod.validate_release_type_for_version(mod.parse_version("0.2.0rc1"), "rc")
    mod.validate_release_type_for_version(mod.parse_version("0.2.0"), "stable")


def test_release_check__emits_manifest_on_success(tmp_path: Path) -> None:
    mod = _load_release_check_module()
    _create_repo(tmp_path)
    _create_prod_safe_run(tmp_path, "core")
    _create_prod_safe_run(tmp_path, "base")
    out_dir = tmp_path / "reports/releases/0.2.0b1"

    rc = mod.run(
        [
            "--version",
            "0.2.0b1",
            "--release-type",
            "beta",
            "--prod-safe-run-core",
            "core",
            "--prod-safe-run-baseline",
            "base",
            "--write-dir",
            str(out_dir),
        ],
        root=tmp_path,
    )
    assert rc == 0

    manifest = json.loads((out_dir / "release_manifest.json").read_text(encoding="utf-8"))
    assert manifest["version"] == "0.2.0b1"
    assert manifest["release_type"] == "beta"
    assert manifest["is_public_release_line"] is True
    assert manifest["checks"]["pyproject_version_match"] is True
    assert manifest["checks"]["changelog_entry"] is True
    assert manifest["checks"]["support_contract_valid"] is True
    assert manifest["checks"]["deprecations_valid"] is True
    assert manifest["blockers"] == []

    readiness = (out_dir / "readiness.md").read_text(encoding="utf-8")
    assert "Release Readiness: 0.2.0b1" in readiness
