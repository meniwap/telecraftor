from __future__ import annotations

import argparse
import subprocess
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_TRACKED_DIRS = (
    ".cursor/",
    ".mypy_cache/",
    ".pytest_cache/",
    ".ruff_cache/",
    ".sessions/",
    ".telecraft/",
    ".venv/",
    "build/",
    "dist/",
    "downloads/",
    "reports/",
    "tests/unit/fixtures/tl/",
    "apps/manual_labs/",
    "apps/streamingbot/",
)
FORBIDDEN_TRACKED_EXACT = {
    ".DS_Store",
    ".env",
    "cachkl",
    "apps/env.sh",
    "apps/bot_config.json",
}
FORBIDDEN_SUFFIXES = (
    ".db",
    ".log",
    ".pyo",
    ".pyc",
    ".session.json",
    ".sqlite",
    ".sqlite3",
)

FORBIDDEN_ARTIFACT_DIRS = (
    ".cursor/",
    ".mypy_cache/",
    ".pytest_cache/",
    ".ruff_cache/",
    ".sessions/",
    ".telecraft/",
    ".venv/",
    "build/",
    "dist/",
    "downloads/",
    "reports/",
    "tests/unit/fixtures/tl/",
    "apps/manual_labs/",
    "apps/streamingbot/",
)
BROKEN_REFERENCES = (
    "tests/live/test_aggressive_suite.py",
    "tests/live/test_integration_manual.py",
    "apps/manual_labs",
    "apps/streamingbot",
)
REFERENCE_SCAN_EXCLUDES = {
    ".gitignore",
    "tools/check_repo_hygiene.py",
}


def _git_ls_files() -> list[str]:
    proc = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    raw = proc.stdout.decode("utf-8")
    return [item for item in raw.split("\0") if item]


def _has_pycache_part(path: str) -> bool:
    return "__pycache__" in PurePosixPath(path).parts


def _forbidden_tracked_reason(path: str) -> str | None:
    if path in FORBIDDEN_TRACKED_EXACT:
        return "forbidden tracked local/runtime file"
    if _has_pycache_part(path):
        return "forbidden tracked __pycache__ path"
    if path.endswith(FORBIDDEN_SUFFIXES):
        return "forbidden tracked generated artifact"
    for prefix in FORBIDDEN_TRACKED_DIRS:
        if path.startswith(prefix):
            return f"forbidden tracked path under {prefix}"
    return None


def _forbidden_artifact_reason(path: str) -> str | None:
    if path in FORBIDDEN_TRACKED_EXACT:
        return "forbidden local/runtime file in package artifact"
    if _has_pycache_part(path):
        return "forbidden __pycache__ path in package artifact"
    if path.endswith(FORBIDDEN_SUFFIXES):
        return "forbidden generated artifact in package artifact"
    for prefix in FORBIDDEN_ARTIFACT_DIRS:
        if path.startswith(prefix):
            return f"forbidden path under {prefix} in package artifact"
    return None


def _unexpected_artifact_member_reason(artifact: Path, path: str) -> str | None:
    """Fail closed when a distribution contains anything outside its public package roots."""
    parts = PurePosixPath(path).parts
    if not parts:
        return None

    if artifact.suffix == ".whl":
        root = parts[0]
        if root == "telecraft" or (
            root.startswith("telecraft-") and root.endswith(".dist-info")
        ):
            return None
        return "unexpected path outside telecraft package or distribution metadata"

    if artifact.name.endswith(".tar.gz"):
        allowed_exact = {
            ".gitignore",
            "CHANGELOG.md",
            "LICENSE",
            "PKG-INFO",
            "README.md",
            "pyproject.toml",
            "src",
            "src/telecraft",
        }
        if path in allowed_exact or path.startswith("src/telecraft/"):
            return None
        return "unexpected path outside the source package allow-list"

    return "unsupported artifact type"


def _check_tracked_paths(paths: list[str]) -> list[str]:
    errors: list[str] = []
    for path in paths:
        reason = _forbidden_tracked_reason(path)
        if reason:
            errors.append(f"{path}: {reason}")
    return errors


def _check_references(paths: list[str]) -> list[str]:
    errors: list[str] = []
    for path in paths:
        if path in REFERENCE_SCAN_EXCLUDES:
            continue
        full_path = ROOT / path
        if not full_path.is_file():
            continue
        try:
            text = full_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for reference in BROKEN_REFERENCES:
            if reference in text:
                errors.append(f"{path}: stale reference to {reference!r}")
    return errors


def _normalize_artifact_member(path: str, *, strip_project_root: bool) -> str:
    normalized = path.replace("\\", "/").lstrip("/")
    parts = [part for part in normalized.split("/") if part]
    if strip_project_root and len(parts) > 1 and parts[0].startswith("telecraft-"):
        return "/".join(parts[1:])
    return "/".join(parts)


def _artifact_members(path: Path) -> list[str]:
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as zf:
            return [
                _normalize_artifact_member(name, strip_project_root=False)
                for name in zf.namelist()
            ]
    if path.name.endswith(".tar.gz"):
        with tarfile.open(path, "r:gz") as tf:
            return [
                _normalize_artifact_member(member.name, strip_project_root=True)
                for member in tf.getmembers()
            ]
    raise ValueError(f"Unsupported artifact type: {path}")


def _check_artifacts(paths: list[Path]) -> list[str]:
    errors: list[str] = []
    for artifact in paths:
        if not artifact.exists():
            errors.append(f"{artifact}: artifact does not exist")
            continue
        for member in _artifact_members(artifact):
            reason = _forbidden_artifact_reason(member)
            if reason:
                errors.append(f"{artifact.name}:{member}: {reason}")
                continue
            reason = _unexpected_artifact_member_reason(artifact, member)
            if reason:
                errors.append(f"{artifact.name}:{member}: {reason}")
    return errors


def _default_artifacts() -> list[Path]:
    dist = ROOT / "dist"
    return sorted([*dist.glob("*.tar.gz"), *dist.glob("*.whl")])


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check Telecraft repo hygiene.")
    parser.add_argument(
        "--artifacts",
        action="store_true",
        help="Check built package artifacts in dist/ or explicit artifact paths.",
    )
    parser.add_argument("paths", nargs="*", help="Artifact paths to check with --artifacts.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    errors: list[str] = []
    if args.artifacts:
        artifact_paths = [Path(item) for item in args.paths] if args.paths else _default_artifacts()
        if not artifact_paths:
            errors.append("No package artifacts found to check.")
        errors.extend(_check_artifacts(artifact_paths))
    else:
        paths = _git_ls_files()
        errors.extend(_check_tracked_paths(paths))
        errors.extend(_check_references(paths))

    if errors:
        print("Repo hygiene failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Repo hygiene passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
