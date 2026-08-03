from __future__ import annotations

import pytest

from telecraft.mtproto.auth.handshake import (
    AuthHandshakeError,
    _validate_dh_gen_response,
    _validate_known_nonces,
    _validate_server_dh_params_response,
)
from telecraft.mtproto.auth.kdf import new_nonce_hash
from telecraft.mtproto.crypto.hashes import sha1
from telecraft.tl.generated.types import (
    DhGenFail,
    DhGenOk,
    DhGenRetry,
    ServerDhInnerData,
    ServerDhParamsFail,
    ServerDhParamsOk,
)

_NONCE = b"\x01" * 16
_SERVER_NONCE = b"\x02" * 16
_NEW_NONCE = b"\x03" * 32
_AUTH_KEY = b"\x04" * 256


def _validate_server_response(response: object) -> ServerDhParamsOk:
    return _validate_server_dh_params_response(
        response,
        nonce=_NONCE,
        server_nonce=_SERVER_NONCE,
        new_nonce=_NEW_NONCE,
    )


def _validate_final_response(response: object) -> DhGenOk | DhGenRetry:
    return _validate_dh_gen_response(
        response,
        nonce=_NONCE,
        server_nonce=_SERVER_NONCE,
        new_nonce=_NEW_NONCE,
        auth_key=_AUTH_KEY,
    )


def _server_inner(
    *,
    nonce: bytes = _NONCE,
    server_nonce: bytes = _SERVER_NONCE,
) -> ServerDhInnerData:
    return ServerDhInnerData(
        nonce=nonce,
        server_nonce=server_nonce,
        g=3,
        dh_prime=b"prime",
        g_a=b"public",
        server_time=123456,
    )


def test_validate_server_dh_inner_accepts_expected_nonces() -> None:
    _validate_known_nonces(
        _server_inner(),
        response_name="server_DH_inner_data",
        nonce=_NONCE,
        server_nonce=_SERVER_NONCE,
    )


@pytest.mark.parametrize(
    ("inner", "message"),
    [
        (_server_inner(nonce=b"\xff" * 16), "server_DH_inner_data.nonce mismatch"),
        (
            _server_inner(server_nonce=b"\xff" * 16),
            "server_DH_inner_data.server_nonce mismatch",
        ),
    ],
)
def test_validate_server_dh_inner_rejects_nonce_mismatch(
    inner: ServerDhInnerData,
    message: str,
) -> None:
    with pytest.raises(AuthHandshakeError, match=message):
        _validate_known_nonces(
            inner,
            response_name="server_DH_inner_data",
            nonce=_NONCE,
            server_nonce=_SERVER_NONCE,
        )


def test_validate_server_dh_params_ok_accepts_expected_nonces() -> None:
    response = ServerDhParamsOk(
        nonce=_NONCE,
        server_nonce=_SERVER_NONCE,
        encrypted_answer=b"encrypted later",
    )

    assert _validate_server_response(response) is response


@pytest.mark.parametrize(
    ("nonce", "server_nonce", "message"),
    [
        (b"\xff" * 16, _SERVER_NONCE, "server_DH_params_ok.nonce mismatch"),
        (_NONCE, b"\xff" * 16, "server_DH_params_ok.server_nonce mismatch"),
    ],
)
def test_validate_server_dh_params_ok_rejects_nonce_mismatch(
    nonce: bytes,
    server_nonce: bytes,
    message: str,
) -> None:
    response = ServerDhParamsOk(
        nonce=nonce,
        server_nonce=server_nonce,
        encrypted_answer=b"encrypted later",
    )

    with pytest.raises(AuthHandshakeError, match=message):
        _validate_server_response(response)


def test_validate_server_dh_params_fail_accepts_fields_then_reports_failure() -> None:
    response = ServerDhParamsFail(
        nonce=_NONCE,
        server_nonce=_SERVER_NONCE,
        new_nonce_hash=sha1(_NEW_NONCE)[4:20],
    )

    with pytest.raises(AuthHandshakeError, match="Server returned server_DH_params_fail"):
        _validate_server_response(response)


def test_validate_server_dh_params_fail_rejects_new_nonce_hash_mismatch() -> None:
    response = ServerDhParamsFail(
        nonce=_NONCE,
        server_nonce=_SERVER_NONCE,
        new_nonce_hash=b"\xff" * 16,
    )

    with pytest.raises(AuthHandshakeError, match="new_nonce_hash mismatch"):
        _validate_server_response(response)


def test_validate_server_dh_params_rejects_unexpected_response() -> None:
    with pytest.raises(AuthHandshakeError, match="Unexpected response to req_DH_params"):
        _validate_server_response(object())


def test_validate_dh_gen_ok_accepts_expected_nonces_and_hash() -> None:
    response = DhGenOk(
        nonce=_NONCE,
        server_nonce=_SERVER_NONCE,
        new_nonce_hash1=new_nonce_hash(
            new_nonce=_NEW_NONCE,
            auth_key=_AUTH_KEY,
            number=1,
        ),
    )

    assert _validate_final_response(response) is response


@pytest.mark.parametrize(
    ("nonce", "server_nonce", "message"),
    [
        (b"\xff" * 16, _SERVER_NONCE, "DhGenOk.nonce mismatch"),
        (_NONCE, b"\xff" * 16, "DhGenOk.server_nonce mismatch"),
    ],
)
def test_validate_dh_gen_ok_rejects_nonce_mismatch(
    nonce: bytes,
    server_nonce: bytes,
    message: str,
) -> None:
    response = DhGenOk(
        nonce=nonce,
        server_nonce=server_nonce,
        new_nonce_hash1=new_nonce_hash(
            new_nonce=_NEW_NONCE,
            auth_key=_AUTH_KEY,
            number=1,
        ),
    )

    with pytest.raises(AuthHandshakeError, match=message):
        _validate_final_response(response)


def test_validate_dh_gen_ok_rejects_hash_mismatch() -> None:
    response = DhGenOk(
        nonce=_NONCE,
        server_nonce=_SERVER_NONCE,
        new_nonce_hash1=b"\xff" * 16,
    )

    with pytest.raises(AuthHandshakeError, match="new_nonce_hash1 mismatch"):
        _validate_final_response(response)


def test_validate_dh_gen_retry_accepts_expected_nonces_and_hash() -> None:
    response = DhGenRetry(
        nonce=_NONCE,
        server_nonce=_SERVER_NONCE,
        new_nonce_hash2=new_nonce_hash(
            new_nonce=_NEW_NONCE,
            auth_key=_AUTH_KEY,
            number=2,
        ),
    )

    assert _validate_final_response(response) is response


def test_validate_dh_gen_fail_accepts_fields_then_reports_failure() -> None:
    response = DhGenFail(
        nonce=_NONCE,
        server_nonce=_SERVER_NONCE,
        new_nonce_hash3=new_nonce_hash(
            new_nonce=_NEW_NONCE,
            auth_key=_AUTH_KEY,
            number=3,
        ),
    )

    with pytest.raises(AuthHandshakeError, match="Server returned dh_gen_fail"):
        _validate_final_response(response)


@pytest.mark.parametrize(
    "response",
    [
        DhGenRetry(
            nonce=_NONCE,
            server_nonce=_SERVER_NONCE,
            new_nonce_hash2=b"\xff" * 16,
        ),
        DhGenFail(
            nonce=_NONCE,
            server_nonce=_SERVER_NONCE,
            new_nonce_hash3=b"\xff" * 16,
        ),
    ],
)
def test_validate_dh_gen_retry_and_fail_reject_hash_mismatch(response: object) -> None:
    with pytest.raises(AuthHandshakeError, match="new_nonce_hash[23] mismatch"):
        _validate_final_response(response)


def test_validate_dh_gen_rejects_unexpected_response() -> None:
    with pytest.raises(AuthHandshakeError, match="Unexpected response to set_client_DH_params"):
        _validate_final_response(object())
