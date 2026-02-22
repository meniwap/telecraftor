from __future__ import annotations

import json
from pathlib import Path

import pytest

from telecraft.client.runtime_isolation import (
    RuntimeIsolationError,
    default_session_path,
    pick_existing_session,
    require_prod_override,
    resolve_session_kind,
    resolve_runtime,
    resolve_session_paths,
    validate_session_matches_network,
    write_current_session_pointer,
)


def _write_session(path: Path, *, host: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "dc_id": 2,
        "host": host,
        "port": 443,
        "framing": "intermediate",
        "auth_key_b64": "",
        "server_salt_hex": "",
        "session_id_hex": None,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_runtime_isolation__resolve_runtime__defaults_to_sandbox() -> None:
    assert resolve_runtime(None) == "sandbox"
    assert resolve_runtime("") == "sandbox"


def test_runtime_isolation__require_prod_override__fails_without_flag_or_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TELECRAFT_ALLOW_PROD_LIVE", raising=False)
    with pytest.raises(RuntimeIsolationError):
        require_prod_override(
            allow_flag=False,
            env_var="TELECRAFT_ALLOW_PROD_LIVE",
            action="live tests on production Telegram",
            example="cmd ...",
        )


def test_runtime_isolation__require_prod_override__passes_with_flag_and_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TELECRAFT_ALLOW_PROD_LIVE", "1")
    require_prod_override(
        allow_flag=True,
        env_var="TELECRAFT_ALLOW_PROD_LIVE",
        action="live tests on production Telegram",
        example="cmd ...",
    )


def test_runtime_isolation__validate_session_matches_network__rejects_prod_session_on_test(
    tmp_path: Path,
) -> None:
    session = tmp_path / "prod_dc4.session.json"
    _write_session(session, host="149.154.167.91")
    with pytest.raises(RuntimeIsolationError):
        validate_session_matches_network(session_path=session, expected_network="test")


def test_runtime_isolation__validate_session_matches_network__rejects_test_session_on_prod(
    tmp_path: Path,
) -> None:
    session = tmp_path / "test_dc2.session.json"
    _write_session(session, host="149.154.167.40")
    with pytest.raises(RuntimeIsolationError):
        validate_session_matches_network(session_path=session, expected_network="prod")


def test_runtime_isolation__resolve_session_paths__separate_roots(tmp_path: Path) -> None:
    sandbox_paths = resolve_session_paths(runtime="sandbox", network="test", sessions_root=tmp_path)
    prod_paths = resolve_session_paths(runtime="prod", network="prod", sessions_root=tmp_path)

    assert sandbox_paths.runtime_root == tmp_path / "sandbox"
    assert sandbox_paths.current_pointer == tmp_path / "sandbox" / "current"
    assert sandbox_paths.current_bot_pointer == tmp_path / "sandbox" / "current_bot"
    assert sandbox_paths.audit_peer_file == tmp_path / "sandbox" / "live_audit_peer.txt"

    assert prod_paths.runtime_root == tmp_path / "prod"
    assert prod_paths.current_pointer == tmp_path / "prod" / "current"
    assert prod_paths.current_bot_pointer == tmp_path / "prod" / "current_bot"
    assert prod_paths.audit_peer_file == tmp_path / "prod" / "live_audit_peer.txt"


def test_runtime_isolation__resolve_session_kind__supports_user_and_bot() -> None:
    assert resolve_session_kind(None) == "user"
    assert resolve_session_kind("user") == "user"
    assert resolve_session_kind("bot") == "bot"
    with pytest.raises(RuntimeIsolationError):
        resolve_session_kind("unknown")


def test_runtime_isolation__default_session_path__separates_user_and_bot(tmp_path: Path) -> None:
    paths = resolve_session_paths(runtime="sandbox", network="test", sessions_root=tmp_path)
    user_path = default_session_path(paths, dc=2, kind="user")
    bot_path = default_session_path(paths, dc=2, kind="bot")
    assert user_path.name == "test_dc2.session.json"
    assert bot_path.name == "test_dc2.bot.session.json"


def test_runtime_isolation__pick_existing_session__uses_kind_specific_pointer(tmp_path: Path) -> None:
    paths = resolve_session_paths(runtime="sandbox", network="test", sessions_root=tmp_path)
    user_session = tmp_path / "sandbox" / "test_dc2.session.json"
    bot_session = tmp_path / "sandbox" / "test_dc2.bot.session.json"
    _write_session(user_session, host="149.154.167.40")
    _write_session(bot_session, host="149.154.167.40")

    write_current_session_pointer(paths, user_session, kind="user")
    write_current_session_pointer(paths, bot_session, kind="bot")

    picked_user = pick_existing_session(paths, preferred_dc=2, kind="user")
    picked_bot = pick_existing_session(paths, preferred_dc=2, kind="bot")
    assert picked_user == str(user_session.resolve())
    assert picked_bot == str(bot_session.resolve())
