from __future__ import annotations

import asyncio

import pytest

from telecraft.mtproto.auth import handshake
from telecraft.mtproto.auth.dh import DhResult
from telecraft.mtproto.auth.handshake import AuthHandshakeError
from telecraft.mtproto.auth.kdf import auth_key_aux_hash, new_nonce_hash, tmp_aes_key_iv
from telecraft.mtproto.core.msg_id import MsgIdGenerator
from telecraft.mtproto.crypto.aes_ige import AesIge
from telecraft.tl.codec import loads
from telecraft.tl.generated.functions import SetClientDhParams
from telecraft.tl.generated.types import ClientDhInnerData, DhGenOk, DhGenRetry

_NONCE = b"\x01" * 16
_SERVER_NONCE = b"\x02" * 16
_NEW_NONCE = b"\x03" * 32


def _dh_result(marker: int) -> DhResult:
    auth_key = bytes([marker]) * 256
    return DhResult(
        auth_key=auth_key,
        auth_key_id=b"k" * 8,
        g_b=bytes([marker + 16]) * 256,
    )


def _decrypt_client_inner(request: SetClientDhParams) -> ClientDhInnerData:
    key, iv = tmp_aes_key_iv(new_nonce=_NEW_NONCE, server_nonce=_SERVER_NONCE)
    encrypted = request.encrypted_data
    assert isinstance(encrypted, bytes)
    plain = AesIge(key=key, iv=iv).decrypt(encrypted)
    # Client-DH encrypted data is padded with random bytes to an AES block;
    # this is the one audited TL boundary where trailing bytes are expected.
    inner = loads(plain[20:], allow_trailing=True)
    assert isinstance(inner, ClientDhInnerData)
    return inner


def test_complete_client_dh_exchange_retries_with_new_b_and_previous_aux_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dh_results = [_dh_result(1), _dh_result(2)]
    make_calls: list[DhResult] = []
    requests: list[SetClientDhParams] = []

    def fake_make_dh_result(*, g: int, dh_prime: bytes, g_a: bytes) -> DhResult:
        assert (g, dh_prime, g_a) == (3, b"prime", b"g-a")
        result = dh_results[len(make_calls)]
        make_calls.append(result)
        return result

    async def fake_send_unencrypted_request(
        transport: object,
        msg_id_gen: MsgIdGenerator,
        request: object,
    ) -> object:
        _ = transport, msg_id_gen
        assert isinstance(request, SetClientDhParams)
        requests.append(request)
        auth_key = dh_results[len(requests) - 1].auth_key
        if len(requests) == 1:
            return DhGenRetry(
                nonce=_NONCE,
                server_nonce=_SERVER_NONCE,
                new_nonce_hash2=new_nonce_hash(
                    new_nonce=_NEW_NONCE,
                    auth_key=auth_key,
                    number=2,
                ),
            )
        return DhGenOk(
            nonce=_NONCE,
            server_nonce=_SERVER_NONCE,
            new_nonce_hash1=new_nonce_hash(
                new_nonce=_NEW_NONCE,
                auth_key=auth_key,
                number=1,
            ),
        )

    monkeypatch.setattr(handshake, "make_dh_result", fake_make_dh_result)
    monkeypatch.setattr(
        handshake,
        "_send_unencrypted_request",
        fake_send_unencrypted_request,
    )

    result = asyncio.run(
        handshake._complete_client_dh_exchange(
            object(),  # type: ignore[arg-type]
            MsgIdGenerator(),
            nonce=_NONCE,
            server_nonce=_SERVER_NONCE,
            new_nonce=_NEW_NONCE,
            g=3,
            dh_prime=b"prime",
            g_a=b"g-a",
        )
    )

    assert result is dh_results[1]
    assert make_calls == dh_results
    assert len(requests) == 2

    first_inner = _decrypt_client_inner(requests[0])
    second_inner = _decrypt_client_inner(requests[1])
    assert first_inner.retry_id == 0
    assert first_inner.g_b == dh_results[0].g_b
    assert second_inner.retry_id == int.from_bytes(
        auth_key_aux_hash(dh_results[0].auth_key),
        "little",
        signed=True,
    )
    assert second_inner.g_b == dh_results[1].g_b


def test_complete_client_dh_exchange_limits_server_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    make_calls = 0

    def fake_make_dh_result(*, g: int, dh_prime: bytes, g_a: bytes) -> DhResult:
        nonlocal make_calls
        _ = g, dh_prime, g_a
        make_calls += 1
        return _dh_result(make_calls)

    async def always_retry(
        transport: object,
        msg_id_gen: MsgIdGenerator,
        request: object,
    ) -> DhGenRetry:
        _ = transport, msg_id_gen, request
        auth_key = bytes([make_calls]) * 256
        return DhGenRetry(
            nonce=_NONCE,
            server_nonce=_SERVER_NONCE,
            new_nonce_hash2=new_nonce_hash(
                new_nonce=_NEW_NONCE,
                auth_key=auth_key,
                number=2,
            ),
        )

    monkeypatch.setattr(handshake, "make_dh_result", fake_make_dh_result)
    monkeypatch.setattr(handshake, "_send_unencrypted_request", always_retry)

    with pytest.raises(AuthHandshakeError, match="too many dh_gen_retry"):
        asyncio.run(
            handshake._complete_client_dh_exchange(
                object(),  # type: ignore[arg-type]
                MsgIdGenerator(),
                nonce=_NONCE,
                server_nonce=_SERVER_NONCE,
                new_nonce=_NEW_NONCE,
                g=3,
                dh_prime=b"prime",
                g_a=b"g-a",
                max_retries=1,
            )
        )

    assert make_calls == 2
