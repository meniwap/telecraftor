from __future__ import annotations

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from telecraft.mtproto.auth.handshake import (
    AuthHandshakeError,
    decrypt_server_dh_inner,
    rsa_encrypt_inner_data,
)
from telecraft.mtproto.auth.kdf import tmp_aes_key_iv
from telecraft.mtproto.crypto.aes_ige import AesIge
from telecraft.mtproto.crypto.hashes import sha1
from telecraft.mtproto.crypto.rsa import RsaPublicKey
from telecraft.tl.codec import dumps
from telecraft.tl.generated.types import PQInnerData, ServerDhInnerData, ServerDhParamsOk


def _encrypted_server_dh_answer(
    inner: ServerDhInnerData,
    *,
    new_nonce: bytes,
    server_nonce: bytes,
    digest: bytes | None = None,
    extra_padding: int = 0,
) -> bytes:
    data = dumps(inner)
    plaintext = (sha1(data) if digest is None else digest) + data
    pad_len = (-len(plaintext)) % 16
    plaintext += b"\xa5" * (pad_len + extra_padding)
    key, iv = tmp_aes_key_iv(new_nonce=new_nonce, server_nonce=server_nonce)
    return AesIge(key=key, iv=iv).encrypt(plaintext)


def test_decrypt_server_dh_inner_strips_sha1_prefix() -> None:
    new_nonce = b"\x11" * 32
    nonce = b"\x01" * 16
    server_nonce = b"\x02" * 16

    inner = ServerDhInnerData(
        nonce=nonce,
        server_nonce=server_nonce,
        g=3,
        dh_prime=b"\x03" * 64,
        g_a=b"\x04" * 64,
        server_time=123456,
    )

    server_dh = ServerDhParamsOk(
        nonce=nonce,
        server_nonce=server_nonce,
        encrypted_answer=_encrypted_server_dh_answer(
            inner,
            new_nonce=new_nonce,
            server_nonce=server_nonce,
        ),
    )

    out = decrypt_server_dh_inner(server_dh, new_nonce=new_nonce)
    assert out == inner


def test_decrypt_server_dh_inner_rejects_sha1_mismatch() -> None:
    new_nonce = b"\x11" * 32
    nonce = b"\x01" * 16
    server_nonce = b"\x02" * 16
    inner = ServerDhInnerData(
        nonce=nonce,
        server_nonce=server_nonce,
        g=3,
        dh_prime=b"\x03" * 64,
        g_a=b"\x04" * 64,
        server_time=123456,
    )
    server_dh = ServerDhParamsOk(
        nonce=nonce,
        server_nonce=server_nonce,
        encrypted_answer=_encrypted_server_dh_answer(
            inner,
            new_nonce=new_nonce,
            server_nonce=server_nonce,
            digest=b"\x00" * 20,
        ),
    )

    with pytest.raises(AuthHandshakeError, match="SHA1 mismatch"):
        decrypt_server_dh_inner(server_dh, new_nonce=new_nonce)


def test_decrypt_server_dh_inner_rejects_more_than_15_padding_bytes() -> None:
    new_nonce = b"\x11" * 32
    nonce = b"\x01" * 16
    server_nonce = b"\x02" * 16
    inner = ServerDhInnerData(
        nonce=nonce,
        server_nonce=server_nonce,
        g=3,
        dh_prime=b"\x03" * 64,
        g_a=b"\x04" * 64,
        server_time=123456,
    )
    server_dh = ServerDhParamsOk(
        nonce=nonce,
        server_nonce=server_nonce,
        encrypted_answer=_encrypted_server_dh_answer(
            inner,
            new_nonce=new_nonce,
            server_nonce=server_nonce,
            extra_padding=16,
        ),
    )

    with pytest.raises(AuthHandshakeError, match="padding length"):
        decrypt_server_dh_inner(server_dh, new_nonce=new_nonce)


def test_decrypt_server_dh_inner_rejects_misaligned_ciphertext() -> None:
    server_dh = ServerDhParamsOk(
        nonce=b"\x01" * 16,
        server_nonce=b"\x02" * 16,
        encrypted_answer=b"\x00" * 15,
    )

    with pytest.raises(AuthHandshakeError, match="positive multiple of 16"):
        decrypt_server_dh_inner(server_dh, new_nonce=b"\x11" * 32)


def test_decrypt_server_dh_inner_rejects_invalid_new_nonce_length() -> None:
    server_dh = ServerDhParamsOk(
        nonce=b"\x01" * 16,
        server_nonce=b"\x02" * 16,
        encrypted_answer=b"\x00" * 16,
    )

    with pytest.raises(AuthHandshakeError, match="new_nonce length mismatch"):
        decrypt_server_dh_inner(server_dh, new_nonce=b"\x11" * 31)


def test_rsa_encrypt_inner_data_uses_mtproto_raw_padding() -> None:
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    der = private.public_key().public_bytes(
        encoding=Encoding.DER,
        format=PublicFormat.SubjectPublicKeyInfo,
    )

    key = RsaPublicKey(der_spki=der)
    inner = PQInnerData(
        pq=b"\x01\x43",
        p=b"\x11",
        q=b"\x13",
        nonce=b"\x01" * 16,
        server_nonce=b"\x02" * 16,
        new_nonce=b"\x03" * 32,
    )

    ct = rsa_encrypt_inner_data(inner, key)
    assert len(ct) == key.key_size_bytes

    priv = private.private_numbers()
    n = priv.public_numbers.n
    d = priv.d
    k = len(ct)

    m_int = pow(int.from_bytes(ct, "big", signed=False), d, n)
    m_bytes = m_int.to_bytes(k, "big", signed=False)

    inner_bytes = dumps(inner)
    assert m_bytes[0] == 0
    padded = m_bytes[1:]
    assert padded[:20] == sha1(inner_bytes)
    assert padded[20 : 20 + len(inner_bytes)] == inner_bytes
