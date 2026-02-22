from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEPRECATIONS_PATH = Path("tests/meta/v2_deprecations.json")
PYPROJECT_PATH = Path("pyproject.toml")
VERSION_RE = re.compile(
    r"^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)(?:(?P<pre>a|b|rc)(?P<pre_n>\d+))?$"
)
PYPROJECT_VERSION_RE = re.compile(r'^version\s*=\s*"([^"]+)"$', re.MULTILINE)


@dataclass(frozen=True, order=True)
class ParsedVersion:
    major: int
    minor: int
    patch: int
    pre_tag: str | None
    pre_num: int | None


def _parse_version(value: str) -> ParsedVersion:
    m = VERSION_RE.match(value.strip())
    if m is None:
        raise AssertionError(f"invalid version: {value!r}")
    pre_tag = m.group("pre")
    pre_num = int(m.group("pre_n")) if m.group("pre_n") else None
    return ParsedVersion(
        major=int(m.group("major")),
        minor=int(m.group("minor")),
        patch=int(m.group("patch")),
        pre_tag=pre_tag,
        pre_num=pre_num,
    )


def _minor_index(v: ParsedVersion) -> int:
    return v.major * 10_000 + v.minor


def _load_deprecations() -> dict[str, Any]:
    data = json.loads(DEPRECATIONS_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise AssertionError("deprecations file must be a top-level object")
    return data


def _current_project_version() -> ParsedVersion:
    raw = PYPROJECT_PATH.read_text(encoding="utf-8")
    m = PYPROJECT_VERSION_RE.search(raw)
    if m is None:
        raise AssertionError("Could not locate [project].version in pyproject.toml")
    return _parse_version(m.group(1))


def test_deprecations__schema_valid() -> None:
    data = _load_deprecations()
    assert data.get("version") == 1
    entries = data.get("deprecations")
    assert isinstance(entries, list)

    for item in entries:
        assert isinstance(item, dict)
        assert isinstance(item.get("symbol"), str) and item["symbol"]
        assert isinstance(item.get("kind"), str) and item["kind"]
        assert isinstance(item.get("deprecated_in"), str)
        assert isinstance(item.get("remove_in"), str)
        assert isinstance(item.get("replacement"), str)
        assert item.get("status") in {"active", "removed"}
        if "notes" in item:
            assert isinstance(item["notes"], str)
        _parse_version(item["deprecated_in"])
        _parse_version(item["remove_in"])


def test_deprecations__symbols_are_unique() -> None:
    data = _load_deprecations()
    seen: set[str] = set()
    dupes: list[str] = []

    for item in data.get("deprecations", []):
        symbol = str(item["symbol"])
        if symbol in seen:
            dupes.append(symbol)
        seen.add(symbol)

    assert not dupes, f"duplicate deprecation symbols: {sorted(dupes)}"


def test_deprecations__remove_in_is_at_least_two_minors_after_deprecated_in() -> None:
    data = _load_deprecations()
    violations: list[str] = []

    for item in data.get("deprecations", []):
        deprecated_in = _parse_version(str(item["deprecated_in"]))
        remove_in = _parse_version(str(item["remove_in"]))
        if _minor_index(remove_in) < _minor_index(deprecated_in) + 2:
            violations.append(
                f"{item['symbol']}: remove_in={item['remove_in']} must be >= +2 minors from "
                f"deprecated_in={item['deprecated_in']}"
            )

    assert not violations, "\n".join(violations)


def test_deprecations__supports_prerelease_versions_for_current_line() -> None:
    assert _parse_version("0.2.0a1") == ParsedVersion(0, 2, 0, "a", 1)
    assert _parse_version("0.2.0b1") == ParsedVersion(0, 2, 0, "b", 1)
    assert _parse_version("0.2.0rc1") == ParsedVersion(0, 2, 0, "rc", 1)
    assert _parse_version("0.2.0") == ParsedVersion(0, 2, 0, None, None)


def test_deprecations__status_removed_requires_due_version_or_explicit_override() -> None:
    data = _load_deprecations()
    current = _current_project_version()
    violations: list[str] = []

    for item in data.get("deprecations", []):
        if item.get("status") != "removed":
            continue
        if bool(item.get("allow_early_removed")):
            continue
        remove_in = _parse_version(str(item["remove_in"]))
        if _minor_index(current) < _minor_index(remove_in):
            violations.append(
                f"{item['symbol']}: status=removed before due version {item['remove_in']} "
                f"(current={current.major}.{current.minor}.{current.patch})"
            )

    assert not violations, "\n".join(violations)
