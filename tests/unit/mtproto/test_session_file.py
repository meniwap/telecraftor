from __future__ import annotations

import pytest

from telecraft.mtproto.session.file import (
    MtprotoSession,
    SessionError,
    SessionInUseError,
    acquire_session_file_lock,
    load_session_file,
    save_session_file,
)


def test_session_file_roundtrip(tmp_path) -> None:
    p = tmp_path / "session.json"
    sess = MtprotoSession(
        dc_id=2,
        host="149.154.167.40",
        port=443,
        framing="intermediate",
        auth_key=b"\x11" * 256,
        server_salt=b"\x22" * 8,
        session_id=b"\x33" * 8,
        updates_state_auth_key_id_alias="0123456789ABCDEF",
    )

    save_session_file(p, sess)
    loaded = load_session_file(p)

    assert loaded.dc_id == sess.dc_id
    assert loaded.host == sess.host
    assert loaded.port == sess.port
    assert loaded.framing == sess.framing
    assert loaded.auth_key == sess.auth_key
    assert loaded.server_salt == sess.server_salt
    assert loaded.session_id == sess.session_id
    assert loaded.updates_state_auth_key_id_alias == "0123456789abcdef"


def test_session_file_rejects_invalid_salt() -> None:
    with pytest.raises(SessionError):
        MtprotoSession(
            dc_id=2,
            host="x",
            port=443,
            framing="intermediate",
            auth_key=b"\x11" * 256,
            server_salt=b"\x22" * 7,
        ).validate()


def test_session_file_accepts_256_byte_auth_key() -> None:
    MtprotoSession(
        dc_id=2,
        host="x",
        port=443,
        framing="intermediate",
        auth_key=b"\x11" * 256,
        server_salt=b"\x22" * 8,
    ).validate()


def test_session_file_lock_rejects_concurrent_owner_and_releases(tmp_path) -> None:
    session_path = tmp_path / "prod.session.json"
    first = acquire_session_file_lock(session_path)
    try:
        with pytest.raises(SessionInUseError, match="already in use"):
            acquire_session_file_lock(session_path)
    finally:
        first.release()

    second = acquire_session_file_lock(session_path)
    second.release()
    assert (tmp_path / "prod.session.json.lock").stat().st_mode & 0o077 == 0


@pytest.mark.parametrize("auth_key", [b"\x11" * 255, b"\x11" * 257, b"\x11" * 31])
def test_session_file_rejects_non_256_byte_auth_key(auth_key: bytes) -> None:
    with pytest.raises(SessionError, match="auth_key"):
        MtprotoSession(
            dc_id=2,
            host="x",
            port=443,
            framing="intermediate",
            auth_key=auth_key,
            server_salt=b"\x22" * 8,
        ).validate()
