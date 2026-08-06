from __future__ import annotations

import base64
import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path


def _load_scanner_module():
    path = Path("tools/check_secrets.py")
    spec = importlib.util.spec_from_file_location("telecraft_tools_check_secrets", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return proc.stdout.strip()


def test_secret_scanner__recognizes_high_signal_credential_shapes() -> None:
    mod = _load_scanner_module()

    private_key = "-----BEGIN " + "PRIVATE KEY-----"
    github_token = "ghp_" + "Ab1C" * 9
    pypi_token = "pypi-" + "AgEIcHlwaS5vcmc" + "Ab1_" * 12
    aws_access_key = "AKIA" + "1A2B3C4D5E6F7G8H"
    aws_secret = ("AWS_" + "SECRET_ACCESS_KEY") + "=" + "aB1/" * 10
    aws_session = ("AWS_" + "SESSION_TOKEN") + "=" + "Ab1_" * 8
    telegram_bot = "123456789:" + "Ab1_-" * 7
    telegram_hash = ("TELEGRAM_" + "API_HASH") + "=" + "0123456789abcdef" + "fedcba9876543210"
    session_auth_key = base64.b64encode(bytes(range(256))).decode("ascii")
    serialized_session = json.dumps({"auth_" + "key_b64": session_auth_key})
    payload = "\n".join(
        (
            private_key,
            github_token,
            pypi_token,
            aws_access_key,
            aws_secret,
            aws_session,
            telegram_bot,
            telegram_hash,
            serialized_session,
        )
    ).encode()

    assert mod._scan_bytes(payload) == {
        "aws_access_key_id",
        "aws_secret_access_key",
        "aws_session_token",
        "github_token",
        "private_key",
        "pypi_token",
        "telegram_bot_token",
        "telegram_literal_credential",
        "telecraft_session_auth_key",
    }


def test_secret_scanner__ignores_nonliteral_assignments_and_known_placeholders() -> None:
    mod = _load_scanner_module()

    payload = b"\n".join(
        (
            b"TELEGRAM_API_HASH=${TELEGRAM_API_HASH}",
            b'TELEGRAM_BOT_TOKEN=os.environ["TELEGRAM_BOT_TOKEN"]',
            b"TELEGRAM_PASSWORD=<read-from-secret-store>",
            ("TELEGRAM_" + "API_HASH=" + "0123456789abcdef" * 2).encode(),
            json.dumps(
                {"auth_" + "key_b64": base64.b64encode(bytes(256)).decode("ascii")}
            ).encode(),
            b"AWS_SECRET_ACCESS_KEY=changeme",
            b"AKIAIOSFODNN7EXAMPLE",
        )
    )

    assert mod._scan_bytes(payload) == set()


def test_secret_scanner__output_contains_metadata_but_never_matched_value(capsys) -> None:
    mod = _load_scanner_module()
    secret = "ghp_" + "Z9yX" * 9
    finding = mod.Finding(
        ref="refs/heads/main",
        blob="1" * 40,
        path="config.txt",
        rule="github_token",
    )

    assert mod._print_result({finding}, scope="test") == 1
    output = capsys.readouterr().out
    assert secret not in output
    metadata = json.loads(output.splitlines()[1])
    assert metadata == {
        "blob": "1" * 40,
        "path": "config.txt",
        "ref": "refs/heads/main",
        "rule": "github_token",
    }


def test_secret_scanner__streaming_detects_a_token_across_chunk_boundaries(monkeypatch) -> None:
    mod = _load_scanner_module()
    monkeypatch.setattr(mod, "_CHUNK_SIZE", 32)
    secret = ("github_" + "pat_") + "Ab1_" * 10
    payload = b"prefix=" + secret.encode() + b"\nsuffix"

    assert mod._scan_stream(io.BytesIO(payload), len(payload)) == {"github_token"}


def test_secret_scanner__history_finds_removed_blob_without_disclosing_value(
    tmp_path: Path,
    capsys,
) -> None:
    mod = _load_scanner_module()
    _git(tmp_path, "init", "-b", "main")
    _git(tmp_path, "config", "user.name", "Telecraft Test")
    _git(tmp_path, "config", "user.email", "test@example.invalid")

    secret = "ghp_" + "Q7wE" * 9
    session_auth_key = base64.b64encode(bytes(range(256))).decode("ascii")
    leaked = tmp_path / "removed.txt"
    leaked_session = tmp_path / "account.json"
    leaked.write_text(secret, encoding="utf-8")
    leaked_session.write_text(
        json.dumps({"auth_" + "key_b64": session_auth_key}),
        encoding="utf-8",
    )
    _git(tmp_path, "add", "removed.txt", "account.json")
    _git(tmp_path, "commit", "-m", "add fixture")
    leaked_commit = _git(tmp_path, "rev-parse", "HEAD")
    leaked_blob = _git(tmp_path, "rev-parse", "HEAD:removed.txt")
    leaked_session_blob = _git(tmp_path, "rev-parse", "HEAD:account.json")

    leaked.write_text("clean\n", encoding="utf-8")
    leaked_session.write_text("{}\n", encoding="utf-8")
    _git(tmp_path, "add", "removed.txt", "account.json")
    _git(tmp_path, "commit", "-m", "remove fixture")
    _git(tmp_path, "tag", "retained-secret", leaked_commit)

    findings = mod._scan_history(tmp_path)
    assert (
        mod.Finding(
            ref="refs/heads/main",
            blob=leaked_blob,
            path="removed.txt",
            rule="github_token",
        )
        in findings
    )
    assert any(
        finding.ref == "refs/tags/retained-secret"
        and finding.blob == leaked_blob
        and finding.rule == "github_token"
        for finding in findings
    )
    assert any(
        finding.ref == "refs/heads/main"
        and finding.blob == leaked_session_blob
        and finding.path == "account.json"
        and finding.rule == "telecraft_session_auth_key"
        for finding in findings
    )

    assert mod._print_result(findings, scope="history test") == 1
    output = capsys.readouterr().out
    assert secret not in output
    assert session_auth_key not in output
    assert leaked_blob in output
    assert "removed.txt" in output


def test_secret_scanner__current_scan_includes_staged_and_untracked_files(tmp_path: Path) -> None:
    mod = _load_scanner_module()
    _git(tmp_path, "init", "-b", "main")
    _git(tmp_path, "config", "user.name", "Telecraft Test")
    _git(tmp_path, "config", "user.email", "test@example.invalid")

    staged_secret = "123456789:" + "Cd2_-" * 7
    staged = tmp_path / "staged.txt"
    staged.write_text(staged_secret, encoding="utf-8")
    _git(tmp_path, "add", "staged.txt")
    staged.write_text("clean worktree\n", encoding="utf-8")

    untracked_secret = "pypi-" + "AgEIcHlwaS5vcmc" + "Ef3_" * 12
    untracked = tmp_path / "untracked.txt"
    untracked.write_text(untracked_secret, encoding="utf-8")

    session_auth_key = base64.b64encode(bytes(range(256))).decode("ascii")
    arbitrary_session = tmp_path / "account.json"
    arbitrary_session.write_text(
        json.dumps({"auth_" + "key_b64": session_auth_key}),
        encoding="utf-8",
    )

    findings = mod._scan_current(tmp_path)
    assert any(
        finding.ref == "INDEX"
        and finding.path == "staged.txt"
        and finding.rule == "telegram_bot_token"
        for finding in findings
    )
    assert any(
        finding.ref == "WORKTREE"
        and finding.path == "account.json"
        and finding.rule == "telecraft_session_auth_key"
        for finding in findings
    )
    assert any(
        finding.ref == "WORKTREE"
        and finding.path == "untracked.txt"
        and finding.rule == "pypi_token"
        for finding in findings
    )
