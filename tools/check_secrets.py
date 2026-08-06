from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

ROOT = Path(__file__).resolve().parents[1]

# Every expression below is bounded. Keeping at least this much overlap makes
# streaming scans deterministic even when a credential crosses a read boundary.
_CHUNK_SIZE = 1024 * 1024
_PATTERN_OVERLAP = 4096


class ScanError(RuntimeError):
    """An operational failure whose message contains metadata only."""


class _Digest(Protocol):
    def update(self, data: bytes) -> None: ...

    def hexdigest(self) -> str: ...


class _Reader(Protocol):
    def read(self, size: int = -1) -> bytes: ...


@dataclass(frozen=True)
class Rule:
    name: str
    pattern: re.Pattern[bytes]
    validator: Callable[[re.Match[bytes]], bool] | None = None


@dataclass(frozen=True, order=True)
class BlobLocation:
    ref: str
    path: str


@dataclass(frozen=True, order=True)
class Finding:
    ref: str
    blob: str
    path: str
    rule: str


def _candidate(match: re.Match[bytes]) -> bytes:
    return match.group("secret")


def _not_aws_example(match: re.Match[bytes]) -> bool:
    value = _candidate(match).upper()
    return not value.endswith(b"EXAMPLE") and len(set(value)) > 4


_PLACEHOLDER_VALUES = {
    b"changeme",
    b"dummy",
    b"example",
    b"fake",
    b"none",
    b"null",
    b"password",
    b"redacted",
    b"replace-me",
    b"replace_me",
    b"sample",
    b"secret",
    b"test",
    b"token",
    b"your-api-hash",
    b"your_api_hash",
}
_PLACEHOLDER_PREFIXES = (
    b"$",
    b"<",
    b"{{",
    b"config.",
    b"env[",
    b"environ",
    b"getenv(",
    b"os.",
    b"secret(",
    b"secrets.",
    b"settings.",
    b"vault.",
)


def _literal_value(match: re.Match[bytes]) -> bytes:
    value = _candidate(match).strip()
    if len(value) >= 2 and value[:1] == value[-1:] and value[:1] in {b"'", b'"'}:
        value = value[1:-1].strip()
    return value


def _is_obvious_placeholder(value: bytes) -> bool:
    lowered = value.lower()
    if not value or lowered in _PLACEHOLDER_VALUES:
        return True
    if lowered.startswith(_PLACEHOLDER_PREFIXES):
        return True
    if b"your" in lowered and b"here" in lowered:
        return True
    if all(byte in b"xX*._-" for byte in value):
        return True
    return False


def _is_literal_credential(match: re.Match[bytes]) -> bool:
    value = _literal_value(match)
    if _is_obvious_placeholder(value):
        return False
    return len(value) >= 8 and len(set(value.lower())) >= 4


def _is_telegram_literal(match: re.Match[bytes]) -> bool:
    key = match.group("key")
    value = _literal_value(match)
    if _is_obvious_placeholder(value):
        return False
    if key.endswith(b"API_ID"):
        # Short sequential IDs are ubiquitous in documentation. Contemporary
        # literal account IDs are longer, which keeps this heuristic high signal.
        return value.isdigit() and 7 <= len(value) <= 20
    if key.endswith(b"API_HASH"):
        return (
            re.fullmatch(rb"[A-Fa-f0-9]{32}", value) is not None
            and value[:16].lower() != value[16:].lower()
        )
    if key.endswith((b"BOT_TOKEN", b"TOKEN")):
        return re.fullmatch(rb"[1-9][0-9]{4,15}:[A-Za-z0-9_-]{30,64}", value) is not None
    if key.endswith((b"CODE", b"PASSCODE")):
        return len(value) >= 5
    if key.endswith((b"PHONE", b"PHONE_NUMBER")):
        return re.fullmatch(rb"\+?[0-9][0-9 ()-]{6,24}", value) is not None
    if key.endswith((b"SESSION", b"SESSION_STRING", b"AUTH_KEY")):
        return len(value) >= 24
    return len(value) >= 8 and len(set(value.lower())) >= 4


def _is_mtproto_auth_key(match: re.Match[bytes]) -> bool:
    value = _literal_value(match)
    if _is_obvious_placeholder(value):
        return False
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        return False
    return len(decoded) == 256 and len(set(decoded)) >= 32


RULES = (
    Rule(
        "private_key",
        re.compile(
            rb"(?P<secret>-----BEGIN[ \t]+(?:(?:RSA|EC|DSA|OPENSSH|ENCRYPTED)[ \t]+)?"
            rb"PRIVATE[ \t]+KEY-----|-----BEGIN[ \t]+PGP[ \t]+PRIVATE[ \t]+KEY[ \t]+BLOCK-----)"
        ),
    ),
    Rule(
        "github_token",
        re.compile(
            rb"(?<![A-Za-z0-9_])(?P<secret>(?:gh[pousr]_[A-Za-z0-9]{36,255}|"
            rb"github_pat_[A-Za-z0-9_]{30,512}))(?![A-Za-z0-9_])"
        ),
    ),
    Rule(
        "pypi_token",
        re.compile(
            rb"(?<![A-Za-z0-9_-])(?P<secret>pypi-AgEIcHlwaS5vcmc[A-Za-z0-9_-]{40,512})"
            rb"(?![A-Za-z0-9_-])"
        ),
    ),
    Rule(
        "aws_access_key_id",
        re.compile(rb"(?<![A-Z0-9])(?P<secret>(?:AKIA|ASIA)[A-Z0-9]{16})(?![A-Z0-9])"),
        _not_aws_example,
    ),
    Rule(
        "aws_secret_access_key",
        re.compile(
            rb"(?im)(?<![A-Za-z0-9_])['\"]?(?:AWS_SECRET_ACCESS_KEY|"
            rb"aws_secret_access_key)['\"]?[ \t]{0,32}(?:=|:)[ \t]{0,32}"
            rb"['\"]?(?P<secret>[A-Za-z0-9/+=]{40})['\"]?(?![A-Za-z0-9/+=])"
        ),
        _is_literal_credential,
    ),
    Rule(
        "aws_session_token",
        re.compile(
            rb"(?im)(?<![A-Za-z0-9_])['\"]?AWS_SESSION_TOKEN['\"]?[ \t]{0,32}"
            rb"(?:=|:)[ \t]{0,32}['\"]?(?P<secret>[A-Za-z0-9/+=_-]{16,2048})"
            rb"['\"]?(?![A-Za-z0-9/+=_-])"
        ),
        _is_literal_credential,
    ),
    Rule(
        "telegram_bot_token",
        re.compile(
            rb"(?<![A-Za-z0-9_-])(?P<secret>[1-9][0-9]{4,15}:[A-Za-z0-9_-]{30,64})"
            rb"(?![A-Za-z0-9_-])"
        ),
    ),
    Rule(
        "telecraft_session_auth_key",
        re.compile(
            rb"(?im)(?<![A-Za-z0-9_])['\"]?auth_key_b64['\"]?[ \t\r\n]{0,32}"
            rb"(?:=|:)[ \t\r\n]{0,32}['\"]?"
            rb"(?P<secret>[A-Za-z0-9+/]{342}==)['\"]?(?![A-Za-z0-9+/=])"
        ),
        _is_mtproto_auth_key,
    ),
    Rule(
        "telegram_literal_credential",
        re.compile(
            rb"(?m)(?<![A-Z0-9_])['\"]?(?P<key>TELEGRAM_(?:API_ID|API_HASH|BOT_TOKEN|"
            rb"TOKEN|PASSWORD|PASSCODE|LOGIN_CODE|CODE|PHONE|PHONE_NUMBER|SESSION|"
            rb"SESSION_STRING|AUTH_KEY|SECRET))['\"]?[ \t]{0,32}(?:=|:)[ \t]{0,32}"
            rb"(?P<secret>\"[^\"\r\n]{1,512}\"|'[^'\r\n]{1,512}'|[^\s#;,]{1,512})"
        ),
        _is_telegram_literal,
    ),
)


def _scan_bytes(data: bytes) -> set[str]:
    findings: set[str] = set()
    for rule in RULES:
        for match in rule.pattern.finditer(data):
            if rule.validator is None or rule.validator(match):
                findings.add(rule.name)
                break
    return findings


def _read_exact(stream: _Reader, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = stream.read(remaining)
        if not chunk:
            raise ScanError("unexpected end of local blob stream")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _scan_stream(
    stream: _Reader,
    size: int,
    *,
    digest: _Digest | None = None,
) -> set[str]:
    findings: set[str] = set()
    tail = b""
    remaining = size
    while remaining:
        chunk = _read_exact(stream, min(_CHUNK_SIZE, remaining))
        remaining -= len(chunk)
        if digest is not None:
            digest.update(chunk)
        window = tail + chunk
        findings.update(_scan_bytes(window))
        tail = window[-_PATTERN_OVERLAP:]
    return findings


def _git(
    root: Path,
    args: list[str],
    *,
    input_data: bytes | None = None,
    allow_failure: bool = False,
) -> bytes:
    proc = subprocess.run(
        ["git", *args],
        cwd=root,
        input=input_data,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if proc.returncode and not allow_failure:
        raise ScanError(f"git metadata command failed: {args[0]}")
    return proc.stdout


def _object_format(root: Path) -> str:
    value = _git(root, ["rev-parse", "--show-object-format"]).strip().decode("ascii")
    if value not in hashlib.algorithms_available:
        raise ScanError("repository uses an unsupported object hash")
    return value


def _git_blob_digest(data_size: int, object_format: str) -> _Digest:
    digest = hashlib.new(object_format)
    digest.update(f"blob {data_size}\0".encode("ascii"))
    return digest


def _worktree_paths(root: Path) -> list[str]:
    raw = _git(root, ["ls-files", "--cached", "--others", "--exclude-standard", "-z", "--"])
    return sorted(
        item.decode("utf-8", errors="surrogateescape") for item in raw.split(b"\0") if item
    )


def _scan_worktree_file(root: Path, path: str, object_format: str) -> tuple[str, set[str]] | None:
    full_path = root / path
    try:
        file_stat = full_path.lstat()
    except FileNotFoundError:
        return None

    if stat.S_ISLNK(file_stat.st_mode):
        data = os.fsencode(os.readlink(full_path))
        digest = _git_blob_digest(len(data), object_format)
        digest.update(data)
        return digest.hexdigest(), _scan_bytes(data)
    if not stat.S_ISREG(file_stat.st_mode):
        return None

    digest = _git_blob_digest(file_stat.st_size, object_format)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(full_path, flags)
    except OSError as exc:
        raise ScanError(f"could not open worktree path: {path!r}") from exc
    with os.fdopen(descriptor, "rb") as stream:
        findings = _scan_stream(stream, file_stat.st_size, digest=digest)
        if stream.read(1):
            raise ScanError(f"worktree path changed while scanning: {path!r}")
    return digest.hexdigest(), findings


def _index_locations(root: Path) -> dict[str, set[BlobLocation]]:
    raw = _git(root, ["ls-files", "--stage", "-z", "--"])
    locations: dict[str, set[BlobLocation]] = {}
    for record in raw.split(b"\0"):
        if not record:
            continue
        metadata, separator, raw_path = record.partition(b"\t")
        fields = metadata.split()
        if not separator or len(fields) != 3 or fields[2] != b"0":
            continue
        oid = fields[1].decode("ascii")
        path = raw_path.decode("utf-8", errors="surrogateescape")
        locations.setdefault(oid, set()).add(BlobLocation("INDEX", path))
    return locations


def _ref_names(root: Path) -> list[str]:
    raw = _git(root, ["for-each-ref", "--format=%(refname)"])
    refs = sorted(
        line.decode("utf-8", errors="surrogateescape") for line in raw.splitlines() if line
    )
    symbolic_head = _git(root, ["symbolic-ref", "-q", "HEAD"], allow_failure=True).strip()
    if not symbolic_head and _git(root, ["rev-parse", "--verify", "HEAD"], allow_failure=True):
        refs.append("HEAD")
    return refs


def _history_locations(root: Path) -> dict[str, set[BlobLocation]]:
    locations: dict[str, set[BlobLocation]] = {}
    for ref in _ref_names(root):
        raw = _git(root, ["rev-list", "--objects", "-z", ref])
        pending_oid: str | None = None
        for record in raw.split(b"\0"):
            if not record:
                continue
            if not record.startswith(b"path="):
                pending_oid = record.decode("ascii")
                continue
            if pending_oid is None:
                raise ScanError("Git returned a path without local object metadata")
            path = record.removeprefix(b"path=").decode("utf-8", errors="surrogateescape")
            locations.setdefault(pending_oid, set()).add(BlobLocation(ref, path))
            pending_oid = None
    return locations


def _blob_types(root: Path, object_ids: Iterable[str]) -> dict[str, str]:
    ordered = sorted(set(object_ids))
    if not ordered:
        return {}
    raw = _git(
        root,
        ["cat-file", "--batch-check=%(objectname) %(objecttype) %(objectsize)"],
        input_data=("\n".join(ordered) + "\n").encode("ascii"),
    )
    types: dict[str, str] = {}
    for line in raw.splitlines():
        fields = line.split()
        if len(fields) == 3:
            types[fields[0].decode("ascii")] = fields[1].decode("ascii")
    if set(ordered) - types.keys():
        raise ScanError("git did not describe every reachable object")
    return types


def _scan_git_locations(
    root: Path,
    locations: dict[str, set[BlobLocation]],
) -> set[Finding]:
    types = _blob_types(root, locations)
    blob_ids = sorted(oid for oid, object_type in types.items() if object_type == "blob")
    if not blob_ids:
        return set()

    proc = subprocess.Popen(
        ["git", "cat-file", "--batch"],
        cwd=root,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    if proc.stdin is None or proc.stdout is None:
        proc.kill()
        raise ScanError("could not open local Git blob reader")

    findings: set[Finding] = set()
    try:
        for oid in blob_ids:
            proc.stdin.write(oid.encode("ascii") + b"\n")
            proc.stdin.flush()
            header = proc.stdout.readline()
            fields = header.split()
            if len(fields) != 3 or fields[0].decode("ascii") != oid or fields[1] != b"blob":
                raise ScanError("Git returned invalid local blob metadata")
            size = int(fields[2])
            rules = _scan_stream(proc.stdout, size)
            if _read_exact(proc.stdout, 1) != b"\n":
                raise ScanError("Git returned an invalid local blob boundary")
            for location in locations[oid]:
                for rule in rules:
                    findings.add(Finding(location.ref, oid, location.path, rule))
        proc.stdin.close()
        if proc.wait() != 0:
            raise ScanError("local Git blob reader failed")
    except BaseException:
        proc.kill()
        proc.wait()
        raise
    finally:
        proc.stdout.close()
    return findings


def _scan_current(root: Path = ROOT) -> set[Finding]:
    object_format = _object_format(root)
    findings = _scan_git_locations(root, _index_locations(root))
    for path in _worktree_paths(root):
        result = _scan_worktree_file(root, path, object_format)
        if result is None:
            continue
        oid, rules = result
        for rule in rules:
            findings.add(Finding("WORKTREE", oid, path, rule))
    return findings


def _scan_history(root: Path = ROOT) -> set[Finding]:
    return _scan_git_locations(root, _history_locations(root))


def _print_result(findings: Iterable[Finding], *, scope: str) -> int:
    ordered = sorted(set(findings))
    if not ordered:
        print(f"Credential scan passed ({scope}).")
        return 0
    print(f"Credential scan failed ({scope}); matched file contents are never displayed:")
    for finding in ordered:
        print(json.dumps(asdict(finding), ensure_ascii=True, sort_keys=True, separators=(",", ":")))
    return 1


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scan local Telecraft files or reachable Git history for credential shapes."
    )
    parser.add_argument(
        "--history",
        action="store_true",
        help="Scan every blob reachable from every local Git ref (never fetches from a remote).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        if args.history:
            return _print_result(_scan_history(), scope="all local Git refs")
        return _print_result(_scan_current(), scope="index and non-ignored worktree")
    except (OSError, ScanError, ValueError):
        # Exception messages are deliberately not forwarded: an unexpected OS or Git
        # diagnostic must not become an accidental credential side channel.
        print(
            "Credential scan could not complete; no matched values were displayed.",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
