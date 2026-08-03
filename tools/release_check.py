from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT_PATH = Path("pyproject.toml")
CHANGELOG_PATH = Path("CHANGELOG.md")
SUPPORT_CONTRACT_PATH = Path("tests/meta/v2_support_contract.json")
DEPRECATIONS_PATH = Path("tests/meta/v2_deprecations.json")
LIVE_EVIDENCE_MAP_PATH = Path("tests/meta/v2_live_evidence_map.json")
REPORTS_LIVE_PROD = Path("reports/live/prod")

VERSION_RE = re.compile(
    r"^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)(?:(?P<pre>a|b|rc)(?P<pre_n>\d+))?$"
)
PYPROJECT_VERSION_RE = re.compile(r'^version\s*=\s*"([^"]+)"$', re.MULTILINE)
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

ALLOWED_SUPPORT_TIER = {"A", "B", "experimental"}
ALLOWED_COMPAT = {"additive+deprecation", "best_effort"}
ALLOWED_LIVE_GATE = {"prod_safe", "none"}
ALLOWED_RELEASE_TYPES = {"alpha", "beta", "rc", "stable"}


class ReleaseCheckError(Exception):
    pass


@dataclass(frozen=True)
class ParsedVersion:
    major: int
    minor: int
    patch: int
    pre_tag: str | None
    pre_num: int | None


@dataclass(frozen=True)
class RunArtifactSummary:
    run_id: str
    source_commit: str
    source_tree_clean: bool
    artifact_sha256: str
    fail_count: int
    cleanup_errors: int
    pass_count: int
    steps: list[str]
    connection_health_probes: dict[str, Any]


@dataclass(frozen=True)
class ReleaseManifest:
    schema_version: int
    version: str
    release_type: str
    tested_commit: str
    is_public_release_line: bool
    checks: dict[str, Any]
    prod_safe_runs: dict[str, Any]
    blockers: list[str]


def parse_version(value: str) -> ParsedVersion:
    m = VERSION_RE.match(value.strip())
    if m is None:
        raise ReleaseCheckError(f"Invalid version format: {value!r}")
    return ParsedVersion(
        major=int(m.group("major")),
        minor=int(m.group("minor")),
        patch=int(m.group("patch")),
        pre_tag=m.group("pre"),
        pre_num=int(m.group("pre_n")) if m.group("pre_n") else None,
    )


def is_public_release_line(version: ParsedVersion) -> bool:
    if version.major >= 1:
        return True
    return version.minor >= 2


def _read_text(root: Path, rel_path: Path) -> str:
    path = root / rel_path
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as ex:
        raise ReleaseCheckError(f"Missing required file: {path}") from ex


def load_pyproject_version(root: Path) -> str:
    raw = _read_text(root, PYPROJECT_PATH)
    m = PYPROJECT_VERSION_RE.search(raw)
    if m is None:
        raise ReleaseCheckError("Could not find [project].version in pyproject.toml")
    return m.group(1)


def validate_local_source_snapshot(root: Path, tested_commit: str) -> None:
    """Bind locally generated live evidence to the clean checkout being inspected."""

    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ReleaseCheckError("Live evidence generation requires a Git checkout") from exc
    if head != tested_commit:
        raise ReleaseCheckError(
            f"tested_commit does not match HEAD: tested={tested_commit}, head={head}"
        )
    if status.strip():
        raise ReleaseCheckError("Live evidence generation requires a clean source tree")


def validate_release_type_for_version(version: ParsedVersion, release_type: str) -> None:
    if release_type not in ALLOWED_RELEASE_TYPES:
        raise ReleaseCheckError(f"Unsupported release type: {release_type}")

    expected_pre = {
        "alpha": "a",
        "beta": "b",
        "rc": "rc",
        "stable": None,
    }[release_type]
    if version.pre_tag != expected_pre:
        raise ReleaseCheckError(
            "release type/version mismatch: "
            f"release_type={release_type!r}, version prerelease={version.pre_tag!r}"
        )


def changelog_has_version(root: Path, version: str) -> bool:
    text = _read_text(root, CHANGELOG_PATH)
    pattern = re.compile(rf"^##\s+\[?{re.escape(version)}\]?(?:\s|-|$)", re.MULTILINE)
    return bool(pattern.search(text))


def _load_json_file(root: Path, rel_path: Path) -> Any:
    text = _read_text(root, rel_path)
    try:
        return json.loads(text)
    except json.JSONDecodeError as ex:
        raise ReleaseCheckError(f"Invalid JSON in {root / rel_path}: {ex}") from ex


def validate_support_contract(root: Path) -> None:
    data = _load_json_file(root, SUPPORT_CONTRACT_PATH)
    if not isinstance(data, dict):
        raise ReleaseCheckError("support contract must be a top-level object")
    if data.get("version") != 1:
        raise ReleaseCheckError("support contract version must be 1")

    for key in ("defaults", "namespace_overrides", "method_overrides"):
        if not isinstance(data.get(key), dict):
            raise ReleaseCheckError(f"support contract field {key!r} must be an object")

    defaults = data["defaults"]
    if set(defaults) != {"stable", "experimental"}:
        raise ReleaseCheckError("support contract defaults must contain stable+experimental")

    for scope_name in ("defaults", "namespace_overrides", "method_overrides"):
        scope = data[scope_name]
        for key, policy in scope.items():
            if not isinstance(policy, dict):
                raise ReleaseCheckError(
                    f"support contract policy {scope_name}.{key} must be object"
                )
            if policy.get("support_tier") not in ALLOWED_SUPPORT_TIER:
                raise ReleaseCheckError(f"invalid support_tier in {scope_name}.{key}")
            if policy.get("compat") not in ALLOWED_COMPAT:
                raise ReleaseCheckError(f"invalid compat in {scope_name}.{key}")
            if policy.get("live_gate") not in ALLOWED_LIVE_GATE:
                raise ReleaseCheckError(f"invalid live_gate in {scope_name}.{key}")


def _minor_index(version: ParsedVersion) -> int:
    return version.major * 10_000 + version.minor


def validate_deprecations(root: Path) -> None:
    data = _load_json_file(root, DEPRECATIONS_PATH)
    if not isinstance(data, dict):
        raise ReleaseCheckError("deprecations file must be a top-level object")
    if data.get("version") != 1:
        raise ReleaseCheckError("deprecations version must be 1")

    entries = data.get("deprecations")
    if not isinstance(entries, list):
        raise ReleaseCheckError("deprecations must be a list")

    seen: set[str] = set()
    current = parse_version(load_pyproject_version(root))

    for idx, item in enumerate(entries):
        if not isinstance(item, dict):
            raise ReleaseCheckError(f"deprecations[{idx}] must be an object")
        symbol = item.get("symbol")
        if not isinstance(symbol, str) or not symbol:
            raise ReleaseCheckError(f"deprecations[{idx}].symbol must be non-empty string")
        if symbol in seen:
            raise ReleaseCheckError(f"duplicate deprecation symbol: {symbol}")
        seen.add(symbol)

        for field in ("kind", "deprecated_in", "remove_in", "replacement"):
            if not isinstance(item.get(field), str):
                raise ReleaseCheckError(f"deprecations[{idx}].{field} must be string")
        if item.get("status") not in {"active", "removed"}:
            raise ReleaseCheckError(f"deprecations[{idx}].status must be active|removed")

        deprecated_in = parse_version(str(item["deprecated_in"]))
        remove_in = parse_version(str(item["remove_in"]))
        if _minor_index(remove_in) < _minor_index(deprecated_in) + 2:
            raise ReleaseCheckError(
                f"deprecation {symbol}: remove_in must be at least +2 minors after deprecated_in"
            )

        if item.get("status") == "removed" and not bool(item.get("allow_early_removed")):
            if _minor_index(current) < _minor_index(remove_in):
                raise ReleaseCheckError(
                    f"deprecation {symbol}: status=removed before due version {item['remove_in']}"
                )


def _load_live_evidence_map(root: Path) -> dict[str, dict[str, Any]]:
    data = _load_json_file(root, LIVE_EVIDENCE_MAP_PATH)
    if not isinstance(data, dict) or data.get("version") != 1:
        raise ReleaseCheckError("live evidence map version must be 1")
    suites = data.get("suites")
    if not isinstance(suites, dict) or set(suites) != {"core", "baseline"}:
        raise ReleaseCheckError("live evidence map must define core and baseline suites")
    for name, suite in suites.items():
        if not isinstance(suite, dict):
            raise ReleaseCheckError(f"live evidence suite {name} must be an object")
        steps = suite.get("required_steps")
        methods = suite.get("stable_methods")
        if (
            not isinstance(steps, list)
            or not steps
            or not all(isinstance(step, str) and step for step in steps)
        ):
            raise ReleaseCheckError(f"live evidence suite {name} has invalid required_steps")
        if (
            not isinstance(methods, list)
            or not methods
            or not all(isinstance(method, str) and method for method in methods)
        ):
            raise ReleaseCheckError(f"live evidence suite {name} has invalid stable_methods")
    return suites


def _artifact_bundle_sha256(required: dict[str, Path]) -> str:
    digest = hashlib.sha256()
    for name, path in sorted(required.items()):
        digest.update(name.encode("ascii"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _load_run_artifacts(
    root: Path,
    run_id: str,
    *,
    required_steps: list[str],
    tested_commit: str,
) -> RunArtifactSummary:
    run_dir = root / REPORTS_LIVE_PROD / run_id
    if not run_dir.exists():
        raise ReleaseCheckError(f"Missing prod-safe run directory: {run_dir}")

    required = {
        "events": run_dir / "events.jsonl",
        "summary": run_dir / "summary.md",
        "artifacts": run_dir / "artifacts.json",
    }
    missing = [str(path) for path in required.values() if not path.exists()]
    if missing:
        raise ReleaseCheckError("Missing prod-safe artifacts:\n- " + "\n- ".join(missing))

    try:
        artifacts_data = json.loads(required["artifacts"].read_text(encoding="utf-8"))
    except json.JSONDecodeError as ex:
        raise ReleaseCheckError(f"Invalid JSON in {required['artifacts']}: {ex}") from ex
    if not isinstance(artifacts_data, dict):
        raise ReleaseCheckError(f"Invalid artifact object in {required['artifacts']}")
    if artifacts_data.get("run_id") != run_id:
        raise ReleaseCheckError(f"prod-safe run ID mismatch in {required['artifacts']}")
    source_commit = artifacts_data.get("source_commit")
    if not isinstance(source_commit, str) or source_commit != tested_commit:
        raise ReleaseCheckError(
            f"prod-safe run {run_id} source_commit does not match tested_commit"
        )
    source_tree_clean = artifacts_data.get("source_tree_clean")
    if source_tree_clean is not True:
        raise ReleaseCheckError(f"prod-safe run {run_id} was not captured from a clean tree")
    fail_count = artifacts_data.get("fail_count")
    if not isinstance(fail_count, int):
        raise ReleaseCheckError(f"Invalid fail_count in {required['artifacts']}")
    if fail_count != 0:
        raise ReleaseCheckError(f"prod-safe run {run_id} has fail_count={fail_count}")

    cleanup_errors = artifacts_data.get("cleanup_errors")
    if not isinstance(cleanup_errors, int) or cleanup_errors != 0:
        raise ReleaseCheckError(
            f"prod-safe run {run_id} has invalid cleanup_errors={cleanup_errors!r}"
        )

    pass_count = artifacts_data.get("pass_count")
    if not isinstance(pass_count, int):
        raise ReleaseCheckError(f"prod-safe run {run_id} has invalid pass_count")

    steps_data = artifacts_data.get("steps")
    if not isinstance(steps_data, list):
        raise ReleaseCheckError(f"prod-safe run {run_id} has invalid steps")
    observed_steps: list[str] = []
    for item in steps_data:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            raise ReleaseCheckError(f"prod-safe run {run_id} has malformed step entry")
        if item.get("status") != "PASS":
            raise ReleaseCheckError(f"prod-safe run {run_id} step {item['name']} did not pass")
        observed_steps.append(str(item["name"]))
    if observed_steps != required_steps:
        raise ReleaseCheckError(
            f"prod-safe run {run_id} step coverage mismatch: "
            f"expected={required_steps!r}, observed={observed_steps!r}"
        )
    if pass_count != len(required_steps):
        raise ReleaseCheckError(f"prod-safe run {run_id} pass_count mismatch: {pass_count}")

    probes = artifacts_data.get("connection_health_probes")
    if not isinstance(probes, dict):
        raise ReleaseCheckError(
            f"prod-safe run {run_id} missing connection_health_probes in artifacts.json"
        )
    if (
        set(probes) != {"enabled", "probe", "pass", "fail"}
        or probes.get("enabled") is not True
        or probes.get("probe") != "profile.me"
        or probes.get("fail") != 0
        or probes.get("pass") != len(required_steps)
    ):
        raise ReleaseCheckError(
            f"prod-safe run {run_id} has invalid connection health probe counts"
        )

    return RunArtifactSummary(
        run_id=run_id,
        source_commit=source_commit,
        source_tree_clean=source_tree_clean,
        artifact_sha256=_artifact_bundle_sha256(required),
        fail_count=fail_count,
        cleanup_errors=cleanup_errors,
        pass_count=pass_count,
        steps=observed_steps,
        connection_health_probes=probes,
    )


def _write_output(write_dir: Path, manifest: ReleaseManifest) -> None:
    write_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = write_dir / "release_manifest.json"
    manifest_path.write_text(
        json.dumps(asdict(manifest), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    readiness_path = write_dir / "readiness.md"
    blockers = manifest.blockers or ["None"]
    lines = [
        f"# Release Readiness: {manifest.version}",
        "",
        f"- release_type: `{manifest.release_type}`",
        f"- public_release_line: `{manifest.is_public_release_line}`",
        f"- ready: `{not manifest.blockers}`",
        "",
        "## Checks",
    ]
    for key, value in manifest.checks.items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Prod-safe runs"])
    for key, value in manifest.prod_safe_runs.items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Blockers"])
    for blocker in blockers:
        lines.append(f"- {blocker}")
    readiness_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def _validate_evidence_run(
    value: object,
    *,
    suite_name: str,
    required_steps: list[str],
    tested_commit: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ReleaseCheckError(f"release evidence suite {suite_name} must be an object")
    allowed_run_fields = {
        "run_id",
        "source_commit",
        "source_tree_clean",
        "artifact_sha256",
        "fail_count",
        "cleanup_errors",
        "pass_count",
        "steps",
        "connection_health_probes",
    }
    if set(value) != allowed_run_fields:
        raise ReleaseCheckError(f"release evidence suite {suite_name} contains unexpected fields")
    run_id = value.get("run_id")
    digest = value.get("artifact_sha256")
    steps = value.get("steps")
    probes = value.get("connection_health_probes")
    if not isinstance(run_id, str) or not run_id:
        raise ReleaseCheckError(f"release evidence suite {suite_name} has invalid run_id")
    if value.get("source_commit") != tested_commit or value.get("source_tree_clean") is not True:
        raise ReleaseCheckError(
            f"release evidence suite {suite_name} is not bound to the tested clean source"
        )
    if not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None:
        raise ReleaseCheckError(f"release evidence suite {suite_name} has invalid artifact_sha256")
    if value.get("fail_count") != 0 or value.get("cleanup_errors") != 0:
        raise ReleaseCheckError(f"release evidence suite {suite_name} reports failures")
    if value.get("pass_count") != len(required_steps) or steps != required_steps:
        raise ReleaseCheckError(f"release evidence suite {suite_name} has incomplete step coverage")
    if not isinstance(probes, dict) or probes.get("fail") != 0:
        raise ReleaseCheckError(f"release evidence suite {suite_name} has failed health probes")
    if set(probes) != {"enabled", "probe", "pass", "fail"}:
        raise ReleaseCheckError(
            f"release evidence suite {suite_name} has unexpected health probe fields"
        )
    if (
        probes.get("enabled") is not True
        or probes.get("probe") != "profile.me"
        or probes.get("pass") != len(required_steps)
    ):
        raise ReleaseCheckError(f"release evidence suite {suite_name} has incomplete health probes")
    return value


def _load_release_evidence(
    root: Path,
    path: Path,
    *,
    version: str,
    release_type: str,
    suites: dict[str, dict[str, Any]],
) -> tuple[str, dict[str, Any]]:
    data = _load_json_file(root, path)
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ReleaseCheckError("release evidence schema_version must be 1")
    allowed_manifest_fields = {
        "schema_version",
        "version",
        "release_type",
        "tested_commit",
        "is_public_release_line",
        "checks",
        "prod_safe_runs",
        "blockers",
    }
    if set(data) != allowed_manifest_fields:
        raise ReleaseCheckError("release evidence contains unexpected fields")
    if data.get("version") != version or data.get("release_type") != release_type:
        raise ReleaseCheckError("release evidence version/release_type mismatch")
    if data.get("is_public_release_line") is not True:
        raise ReleaseCheckError("release evidence is not marked as a public release line")
    tested_commit = data.get("tested_commit")
    if not isinstance(tested_commit, str) or COMMIT_RE.fullmatch(tested_commit) is None:
        raise ReleaseCheckError("release evidence tested_commit must be a full commit SHA")
    if data.get("blockers") != []:
        raise ReleaseCheckError("release evidence contains blockers")

    evidence_checks = data.get("checks")
    required_checks = {
        "pyproject_version_match",
        "changelog_entry",
        "support_contract_valid",
        "deprecations_valid",
        "public_release_line",
        "prod_safe_gate_required",
    }
    if (
        not isinstance(evidence_checks, dict)
        or set(evidence_checks) != required_checks
        or any(evidence_checks.get(name) is not True for name in required_checks)
    ):
        raise ReleaseCheckError("release evidence has incomplete static checks")

    runs = data.get("prod_safe_runs")
    if not isinstance(runs, dict) or set(runs) != {"core", "baseline"}:
        raise ReleaseCheckError("release evidence must contain core and baseline runs")
    validated = {
        name: _validate_evidence_run(
            runs[name],
            suite_name=name,
            required_steps=list(suites[name]["required_steps"]),
            tested_commit=tested_commit,
        )
        for name in ("core", "baseline")
    }
    return tested_commit, validated


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate Telecraft release readiness and emit release manifest artifacts. Internal "
            "0.1.x releases do not require live artifacts; public 0.2.x+ releases require the "
            "remaining prod-safe smoke evidence."
        )
    )
    parser.add_argument("--version", required=True, help="Target package version (e.g. 0.2.0b1)")
    parser.add_argument(
        "--release-type",
        required=True,
        choices=sorted(ALLOWED_RELEASE_TYPES),
        help="Release lane: alpha/beta/rc/stable.",
    )
    parser.add_argument(
        "--prod-safe-run-core",
        default="",
        help="Run ID for prod-safe core smoke report (required for public 0.2.x+ releases).",
    )
    parser.add_argument(
        "--prod-safe-run-baseline",
        default="",
        help="Run ID for prod-safe baseline report (required for public 0.2.x+ releases).",
    )
    parser.add_argument(
        "--tested-commit",
        default="",
        help="Full commit SHA exercised by the local prod-safe runs.",
    )
    parser.add_argument(
        "--evidence-file",
        type=Path,
        default=None,
        help="Validate a previously generated sanitized release manifest instead of local reports.",
    )
    parser.add_argument(
        "--write-dir",
        type=Path,
        required=True,
        help="Directory for release_manifest.json + readiness.md.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate only; do not write output artifacts.",
    )
    return parser


def run(argv: Sequence[str] | None = None, *, root: Path | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    repo_root = ROOT if root is None else Path(root)

    blockers: list[str] = []
    checks: dict[str, Any] = {
        "pyproject_version_match": False,
        "changelog_entry": False,
        "support_contract_valid": False,
        "deprecations_valid": False,
    }
    prod_safe_runs: dict[str, Any] = {
        "core": None,
        "baseline": None,
    }
    tested_commit = ""

    try:
        requested_version = parse_version(args.version)
        validate_release_type_for_version(requested_version, args.release_type)

        pyproject_version = load_pyproject_version(repo_root)
        checks["pyproject_version_match"] = pyproject_version == args.version
        if pyproject_version != args.version:
            raise ReleaseCheckError(
                "pyproject.toml version mismatch: "
                f"pyproject={pyproject_version}, arg={args.version}"
            )

        checks["changelog_entry"] = changelog_has_version(repo_root, args.version)
        if not checks["changelog_entry"]:
            raise ReleaseCheckError(f"CHANGELOG.md missing entry for version {args.version}")

        validate_support_contract(repo_root)
        checks["support_contract_valid"] = True
        validate_deprecations(repo_root)
        checks["deprecations_valid"] = True

        public_line = is_public_release_line(requested_version)
        checks["public_release_line"] = public_line
        checks["prod_safe_gate_required"] = public_line

        if public_line:
            suites = _load_live_evidence_map(repo_root)
            if args.evidence_file is not None:
                tested_commit, prod_safe_runs = _load_release_evidence(
                    repo_root,
                    args.evidence_file,
                    version=args.version,
                    release_type=args.release_type,
                    suites=suites,
                )
            else:
                if not args.prod_safe_run_core.strip() or not args.prod_safe_run_baseline.strip():
                    raise ReleaseCheckError(
                        "Public 0.2.x+ releases require --prod-safe-run-core and "
                        "--prod-safe-run-baseline"
                    )
                tested_commit = args.tested_commit.strip().lower()
                if COMMIT_RE.fullmatch(tested_commit) is None:
                    raise ReleaseCheckError(
                        "Public release evidence requires --tested-commit as a full commit SHA"
                    )
                validate_local_source_snapshot(repo_root, tested_commit)
                core = _load_run_artifacts(
                    repo_root,
                    args.prod_safe_run_core.strip(),
                    required_steps=list(suites["core"]["required_steps"]),
                    tested_commit=tested_commit,
                )
                baseline = _load_run_artifacts(
                    repo_root,
                    args.prod_safe_run_baseline.strip(),
                    required_steps=list(suites["baseline"]["required_steps"]),
                    tested_commit=tested_commit,
                )
                prod_safe_runs["core"] = asdict(core)
                prod_safe_runs["baseline"] = asdict(baseline)
        else:
            tested_commit = "not required for internal 0.1.x line"
            prod_safe_runs["core"] = "not required for internal 0.1.x line"
            prod_safe_runs["baseline"] = "not required for internal 0.1.x line"

    except ReleaseCheckError as ex:
        blockers.append(str(ex))

    manifest = ReleaseManifest(
        schema_version=1,
        version=args.version,
        release_type=args.release_type,
        tested_commit=tested_commit,
        is_public_release_line=bool(checks.get("public_release_line", False)),
        checks=checks,
        prod_safe_runs=prod_safe_runs,
        blockers=blockers,
    )

    if not args.dry_run and not blockers:
        write_dir = args.write_dir
        if not write_dir.is_absolute():
            write_dir = repo_root / write_dir
        _write_output(write_dir, manifest)

    if blockers:
        for blocker in blockers:
            print(f"ERROR: {blocker}", file=sys.stderr)
        return 1

    if args.dry_run:
        print(f"release readiness OK (dry-run): {args.version} [{args.release_type}]")
    else:
        print(f"release readiness OK: {args.version} [{args.release_type}]")
    return 0


def main() -> int:
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
