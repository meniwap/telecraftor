from __future__ import annotations

from dataclasses import dataclass

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from telecraft.mtproto.crypto.rsa import RsaPublicKey


def _der_pkcs1_from_pem(pem: bytes) -> bytes:
    key = serialization.load_pem_public_key(pem)
    if not isinstance(key, rsa.RSAPublicKey):
        raise TypeError("Expected RSA public key")
    return key.public_bytes(encoding=Encoding.DER, format=PublicFormat.PKCS1)


@dataclass(frozen=True, slots=True)
class ServerKeyRing:
    """
    Known Telegram RSA public keys (for auth key exchange).

    Fingerprints are stored as **signed int64**, matching TL "long" decoding.
    """

    keys_by_fingerprint: dict[int, RsaPublicKey]

    def select(self, server_fingerprints: list[int]) -> RsaPublicKey:
        for fp in server_fingerprints:
            key = self.keys_by_fingerprint.get(fp)
            if key is not None:
                return key
        raise KeyError(f"No matching RSA key for server fingerprints: {server_fingerprints!r}")


TELEGRAM_TEST_RSA_PEM = b"""-----BEGIN RSA PUBLIC KEY-----
MIIBCgKCAQEAyMEdY1aR+sCR3ZSJrtztKTKqigvO/vBfqACJLZtS7QMgCGXJ6XIR
yy7mx66W0/sOFa7/1mAZtEoIokDP3ShoqF4fVNb6XeqgQfaUHd8wJpDWHcR2OFwv
plUUI1PLTktZ9uW2WE23b+ixNwJjJGwBDJPQEQFBE+vfmH0JP503wr5INS1poWg/
j25sIWeYPHYeOrFp/eXaqhISP6G+q2IeTaWTXpwZj4LzXq5YOpk4bYEQ6mvRq7D1
aHWfYmlEGepfaYR8Q0YqvvhYtMte3ITnuSJs171+GDqpdKcSwHnd6FudwGO4pcCO
j4WcDuXc2CTHgH8gFTNhp/Y8/SpDOhvn9QIDAQAB
-----END RSA PUBLIC KEY-----
"""

TELEGRAM_MAIN_RSA_PEM = b"""-----BEGIN RSA PUBLIC KEY-----
MIIBCgKCAQEAwVACPi9w23mF3tBkdZz+zwrzKOaaQdr01vAbU4E1pvkfj4sqDsm6
lyDONS789sVoD/xCS9Y0hkkC3gtL1tSfTlgCMOOul9lcixlEKzwKENj1Yz/s7daS
an9tqw3bfUV/nqgbhGX81v/+7RFAEd+RwFnK7a+XYl9sluzHRyVVaTTveB2GazTw
Efzk2DWgkBluml8OREmvfraX3bkHZJTKX4EQSjBbbdJ2ZXIsRrYOXfaA+xayEGB+
8hdlLmAjbCVfaigxX0CDqWeR1yFL9kwd9P0NsZRPsmoqVwMbMu7mStFai6aIhc3n
Slv8kg9qv1m6XHVQY3PnEw+QQtqSIXklHwIDAQAB
-----END RSA PUBLIC KEY-----
"""

_TEST_KEY = RsaPublicKey(der_spki=_der_pkcs1_from_pem(TELEGRAM_TEST_RSA_PEM))
_MAIN_KEY = RsaPublicKey(der_spki=_der_pkcs1_from_pem(TELEGRAM_MAIN_RSA_PEM))

# Fingerprints in Telegram are TL `long` (signed). If you need the canonical *unsigned* form:
#   fp_u64 = fp if fp >= 0 else fp + 2**64
DEFAULT_SERVER_KEYRING = ServerKeyRing(
    keys_by_fingerprint={
        _TEST_KEY.fingerprint: _TEST_KEY,
        _MAIN_KEY.fingerprint: _MAIN_KEY,
    }
)


