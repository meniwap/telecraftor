from __future__ import annotations

import struct
from dataclasses import dataclass

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from telecraft.core.bytes import xor_bytes
from telecraft.mtproto.crypto.aes_ige import AesIge

from .hashes import sha1, sha256


class RsaError(Exception):
    pass


def _tl_bytes(data: bytes) -> bytes:
    """
    TL bytes/string encoding: length + data + 0-padding to 4 bytes.
    """

    ln = len(data)
    if ln < 254:
        out = bytes([ln]) + data
        out += b"\x00" * ((4 - ((1 + ln) % 4)) % 4)
        return out
    out = bytes([254]) + struct.pack("<I", ln)[:3] + data
    out += b"\x00" * ((4 - ((4 + ln) % 4)) % 4)
    return out


def fingerprint_from_der_spki(der_spki: bytes) -> int:
    """
    Compute Telegram-style RSA public key fingerprint.

    Common implementation used by clients:
    - serialize (n, e) as TL-encoded byte strings (TL bytes, concatenated)
    - take SHA1 over the resulting buffer
    - take the last 8 bytes and interpret as little-endian int64 (TL "long" is signed)

    This matches what Telegram servers send in `server_public_key_fingerprints`.
    """

    pub = load_rsa_public_key_der_spki(der_spki)
    nums = pub.public_numbers()

    n = nums.n
    e = nums.e
    n_bytes = n.to_bytes((n.bit_length() + 7) // 8 or 1, "big", signed=False)
    e_bytes = e.to_bytes((e.bit_length() + 7) // 8 or 1, "big", signed=False)

    data = _tl_bytes(n_bytes) + _tl_bytes(e_bytes)
    h = sha1(data)
    return int.from_bytes(h[-8:], "little", signed=True)


def load_rsa_public_key_der_spki(der_spki: bytes) -> rsa.RSAPublicKey:
    key = serialization.load_der_public_key(der_spki)
    if not isinstance(key, rsa.RSAPublicKey):
        raise RsaError("Not an RSA public key")
    return key


def rsa_key_size_bytes(der_spki: bytes) -> int:
    pub = load_rsa_public_key_der_spki(der_spki)
    return (pub.key_size + 7) // 8


def rsa_encrypt_pkcs1v15(der_spki: bytes, plaintext: bytes) -> bytes:
    pub = load_rsa_public_key_der_spki(der_spki)
    try:
        return pub.encrypt(plaintext, padding.PKCS1v15())
    except Exception as e:  # noqa: BLE001
        raise RsaError("RSA encryption failed") from e


def rsa_encrypt_raw(der_spki: bytes, data: bytes) -> bytes:
    """
    Legacy raw RSA helper retained for compatibility/tests.

    The current MTProto auth-key exchange uses RSA-PAD.

    Telegram expects RSA encryption of a 255-byte buffer:
        sha1(data) + data + random_padding
    where random_padding makes the buffer exactly (key_size_bytes - 1) bytes.

    The RSA ciphertext is then exactly key_size_bytes long.
    """

    pub = load_rsa_public_key_der_spki(der_spki)
    numbers = pub.public_numbers()
    n = numbers.n
    e = numbers.e

    k = (pub.key_size + 7) // 8
    if k < 16:
        raise RsaError("RSA key too small")

    target_len = k - 1  # 255 for 2048-bit keys
    prefix = sha1(data) + data
    if len(prefix) > target_len:
        raise RsaError("Data too long for MTProto raw RSA padding")

    # Use OS randomness directly (MTProto requires cryptographically secure random).
    import os

    pad_len = target_len - len(prefix)
    padded = prefix + os.urandom(pad_len)

    m = int.from_bytes(padded, "big", signed=False)
    c = pow(m, e, n)
    return c.to_bytes(k, "big", signed=False)


def rsa_encrypt_rsa_pad(der_spki: bytes, data: bytes) -> bytes:
    """
    Telegram RSA_PAD encryption for req_DH_params.encrypted_data.

    This follows the MTProto auth-key generation spec for 2048-bit server RSA
    keys. The input TL serialization must be at most 144 bytes and the final
    ciphertext is exactly 256 bytes.
    """

    pub = load_rsa_public_key_der_spki(der_spki)
    numbers = pub.public_numbers()
    n = numbers.n
    e = numbers.e
    k = (pub.key_size + 7) // 8
    if k != 256:
        raise RsaError("RSA_PAD requires a 2048-bit RSA key")
    if len(data) > 144:
        raise RsaError("Data too long for MTProto RSA_PAD")

    import os

    data_with_padding = data + os.urandom(192 - len(data))
    data_pad_reversed = data_with_padding[::-1]
    zero_iv = b"\x00" * 32

    for _ in range(256):
        temp_key = os.urandom(32)
        data_with_hash = data_pad_reversed + sha256(temp_key + data_with_padding)
        aes_encrypted = AesIge(key=temp_key, iv=zero_iv).encrypt(data_with_hash)
        temp_key_xor = xor_bytes(temp_key, sha256(aes_encrypted))
        key_aes_encrypted = temp_key_xor + aes_encrypted
        if len(key_aes_encrypted) != 256:
            raise RsaError("RSA_PAD internal length mismatch")
        m = int.from_bytes(key_aes_encrypted, "big", signed=False)
        if m < n:
            c = pow(m, e, n)
            return c.to_bytes(k, "big", signed=False)

    raise RsaError("RSA_PAD failed to produce a value smaller than RSA modulus")


@dataclass(frozen=True, slots=True)
class RsaPublicKey:
    """
    Convenience wrapper used by MTProto auth flow:
    - match key by `fingerprint`
    - encrypt auth data with Telegram RSA_PAD
    """

    der_spki: bytes

    @property
    def fingerprint(self) -> int:
        return fingerprint_from_der_spki(self.der_spki)

    @property
    def key_size_bytes(self) -> int:
        return rsa_key_size_bytes(self.der_spki)

    def encrypt(self, plaintext: bytes) -> bytes:
        return rsa_encrypt_pkcs1v15(self.der_spki, plaintext)

    def encrypt_raw(self, data: bytes) -> bytes:
        return rsa_encrypt_raw(self.der_spki, data)

    def encrypt_rsa_pad(self, data: bytes) -> bytes:
        return rsa_encrypt_rsa_pad(self.der_spki, data)
