from __future__ import annotations

import secrets
from dataclasses import dataclass
from functools import lru_cache

from telecraft.mtproto.crypto.hashes import sha1
from telecraft.mtproto.crypto.random import random_bytes

_DH_VALUE_BYTES = 256
_DH_VALUE_BITS = _DH_VALUE_BYTES * 8
_DH_SAFE_MARGIN_BITS = 64
_VALID_GENERATORS = frozenset({2, 3, 4, 5, 6, 7})
_MILLER_RABIN_ROUNDS = 64
_SMALL_PRIMES = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47)

# Current production dh_prime published by Telegram, in big-endian byte order:
# https://core.telegram.org/mtproto/security_guidelines#validation-of-dh-parameters
# Keeping this known-good value avoids an expensive probable-prime check on every
# normal login while still checking any future server-provided prime below.
_TELEGRAM_DH_PRIME = bytes.fromhex(
    "C71CAEB9C6B1C9048E6C522F70F13F73980D40238E3E21C14934D037563D930F"
    "48198A0AA7C14058229493D22530F4DBFA336F6E0AC925139543AED44CCE7C37"
    "20FD51F69458705AC68CD4FE6B6B13ABDC9746512969328454F18FAF8C595F64"
    "2477FE96BB2A941D5BCD1D4AC8CC49880708FA9B378E3C4F3A9060BEE67CF9A4"
    "A4A695811051907E162753B56B0F6B410DBA74D8A84B2A14B3144E0EF128475"
    "4FD17ED950D5965B4B9DD46582DB1178D169C6BC465B0D6FF9CA3928FEF5B9AE"
    "4E418FC15E83EBEA0F87FA9FF5EED70050DED2849F47BF959D956850CE929851"
    "F0D8115F635B105EE2E4E15D04B2454BF6F4FADF034B10403119CD8E3B92FCC5B"
)


class DhError(Exception):
    pass


def _be_bytes_to_int(data: bytes) -> int:
    return int.from_bytes(data, "big", signed=False)


def _int_to_be_256(*, name: str, n: int) -> bytes:
    if n < 0:
        raise DhError(f"{name} is negative")
    try:
        return n.to_bytes(_DH_VALUE_BYTES, "big", signed=False)
    except OverflowError as e:
        raise DhError(f"{name} does not fit in {_DH_VALUE_BYTES} bytes") from e


def _validate_dh_public_value(*, name: str, value: int, p: int) -> None:
    if value <= 1 or value >= p - 1:
        raise DhError(f"invalid {name}")
    low = 1 << (_DH_VALUE_BITS - _DH_SAFE_MARGIN_BITS)
    if value < low or value > p - low:
        raise DhError(f"unsafe {name}")


def _is_probable_prime(n: int, *, rounds: int = _MILLER_RABIN_ROUNDS) -> bool:
    """Return whether *n* passes a strong Miller-Rabin probable-prime test."""

    if n < 2:
        return False
    for small_prime in _SMALL_PRIMES:
        if n == small_prime:
            return True
        if n % small_prime == 0:
            return False

    d = n - 1
    s = 0
    while d % 2 == 0:
        s += 1
        d //= 2

    for _ in range(rounds):
        base = secrets.randbelow(n - 3) + 2
        x = pow(base, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(s - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


@lru_cache(maxsize=8)
def _is_safe_prime(p: int) -> bool:
    """Check p and (p - 1) / 2 with a 2^-128 Miller-Rabin error bound."""

    return _is_probable_prime(p) and _is_probable_prime((p - 1) // 2)


def _validate_generator(*, g: int, p: int) -> None:
    if g not in _VALID_GENERATORS:
        raise DhError("invalid g")

    # Telegram's quadratic-reciprocity conditions ensure g generates the
    # prime-order subgroup of a safe prime p.
    valid = (
        (g == 2 and p % 8 == 7)
        or (g == 3 and p % 3 == 2)
        or g == 4
        or (g == 5 and p % 5 in (1, 4))
        or (g == 6 and p % 24 in (19, 23))
        or (g == 7 and p % 7 in (3, 5, 6))
    )
    if not valid:
        raise DhError("g is incompatible with dh_prime")


def _validate_dh_params(*, g: int, dh_prime: bytes, g_a: bytes) -> tuple[int, int]:
    if not isinstance(dh_prime, (bytes, bytearray)) or len(dh_prime) != _DH_VALUE_BYTES:
        raise DhError(f"invalid dh_prime length (must be {_DH_VALUE_BYTES} bytes)")

    prime_bytes = bytes(dh_prime)
    p = _be_bytes_to_int(prime_bytes)
    if p <= 0:
        raise DhError("invalid dh_prime")
    if p.bit_length() != _DH_VALUE_BITS:
        raise DhError(f"invalid dh_prime bit length (must be {_DH_VALUE_BITS} bits)")
    _validate_generator(g=g, p=p)
    if prime_bytes != _TELEGRAM_DH_PRIME and not _is_safe_prime(p):
        raise DhError("dh_prime is not a safe prime")

    if not isinstance(g_a, (bytes, bytearray)):
        raise DhError("invalid g_a")
    ga = _be_bytes_to_int(bytes(g_a))
    _validate_dh_public_value(name="g_a", value=ga, p=p)
    return p, ga


def auth_key_id(auth_key: bytes) -> bytes:
    """
    auth_key_id = last 8 bytes of SHA1(auth_key).
    """

    return sha1(auth_key)[-8:]


@dataclass(frozen=True, slots=True)
class DhResult:
    auth_key: bytes
    auth_key_id: bytes  # 8 bytes
    g_b: bytes  # bytes to send in client_DH_inner_data.g_b


def make_dh_result(*, g: int, dh_prime: bytes, g_a: bytes) -> DhResult:
    """
    Compute auth_key and g_b given server parameters.

    This is the "client side" of DH:
    - choose random b
    - g_b = g^b mod dh_prime
    - auth_key = (g_a)^b mod dh_prime
    """

    p, ga = _validate_dh_params(g=g, dh_prime=dh_prime, g_a=g_a)

    # b should be random 256 bytes; using 256 bytes here.
    b = _be_bytes_to_int(random_bytes(_DH_VALUE_BYTES))
    gb_int = pow(g, b, p)
    auth_int = pow(ga, b, p)
    _validate_dh_public_value(name="g_b", value=gb_int, p=p)

    gb = _int_to_be_256(name="g_b", n=gb_int)
    auth = _int_to_be_256(name="auth_key", n=auth_int)
    return DhResult(auth_key=auth, auth_key_id=auth_key_id(auth), g_b=gb)
