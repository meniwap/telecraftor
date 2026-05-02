from __future__ import annotations

from dataclasses import dataclass

from telecraft.mtproto.crypto.hashes import sha1
from telecraft.mtproto.crypto.random import random_bytes

_DH_VALUE_BYTES = 256
_DH_VALUE_BITS = _DH_VALUE_BYTES * 8
_DH_SAFE_MARGIN_BITS = 64
_VALID_GENERATORS = frozenset({2, 3, 4, 5, 6, 7})


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


def _validate_dh_params(*, g: int, dh_prime: bytes, g_a: bytes) -> tuple[int, int]:
    if g not in _VALID_GENERATORS:
        raise DhError("invalid g")
    if not isinstance(dh_prime, (bytes, bytearray)) or len(dh_prime) != _DH_VALUE_BYTES:
        raise DhError(f"invalid dh_prime length (must be {_DH_VALUE_BYTES} bytes)")

    p = _be_bytes_to_int(bytes(dh_prime))
    if p <= 0:
        raise DhError("invalid dh_prime")
    if p.bit_length() != _DH_VALUE_BITS:
        raise DhError(f"invalid dh_prime bit length (must be {_DH_VALUE_BITS} bits)")
    # TODO: Add a known-good Telegram dh_prime whitelist or full safe-prime check.

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
