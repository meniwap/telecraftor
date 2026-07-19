from __future__ import annotations

from hashlib import sha256

import pytest

from telecraft.mtproto.auth import dh
from telecraft.mtproto.auth.dh import DhError, auth_key_id, make_dh_result

_DH_PRIME = dh._TELEGRAM_DH_PRIME
_P = int.from_bytes(_DH_PRIME, "big", signed=False)
_LOW = 1 << (2048 - 64)
_SAFE_GA = _LOW.to_bytes(256, "big", signed=False)


def test_telegram_dh_prime_matches_official_constant() -> None:
    # https://core.telegram.org/mtproto/auth_key#dh-key-exchange-complete
    assert len(_DH_PRIME) == 256
    assert sha256(_DH_PRIME).hexdigest() == (
        "02f85e7687fc6f33ba678226a963b3c8a191b47c890cf30debe17c1d623b5af1"
    )


def _random_b(value: int) -> bytes:
    return value.to_bytes(256, "big", signed=False)


def test_make_dh_result_basic(monkeypatch) -> None:
    monkeypatch.setattr(dh, "random_bytes", lambda _n: _random_b(1984))

    res = make_dh_result(g=3, dh_prime=_DH_PRIME, g_a=_SAFE_GA)
    assert isinstance(res.auth_key, (bytes, bytearray))
    assert len(res.auth_key) == 256
    assert len(res.auth_key_id) == 8
    assert isinstance(res.g_b, (bytes, bytearray))
    assert len(res.g_b) == 256


def test_make_dh_result__pads_leading_zero_auth_key_and_hashes_padded(monkeypatch) -> None:
    def fake_pow(base: int, exp: int, mod: int) -> int:
        _ = exp, mod
        if base == 3:
            return _LOW
        return 1

    monkeypatch.setattr(dh, "random_bytes", lambda _n: _random_b(123456789))
    monkeypatch.setattr(dh, "pow", fake_pow, raising=False)

    res = make_dh_result(g=3, dh_prime=_DH_PRIME, g_a=_SAFE_GA)

    assert len(res.auth_key) == 256
    assert res.auth_key == b"\x00" * 255 + b"\x01"
    assert len(res.g_b) == 256
    assert res.g_b == _LOW.to_bytes(256, "big", signed=False)
    assert res.auth_key_id == auth_key_id(res.auth_key)
    assert res.auth_key_id != auth_key_id(b"\x01")


@pytest.mark.parametrize("g", [0, 1, 8])
def test_make_dh_result__rejects_invalid_g(g: int) -> None:
    with pytest.raises(DhError, match="invalid g"):
        make_dh_result(g=g, dh_prime=_DH_PRIME, g_a=_SAFE_GA)


def test_make_dh_result__rejects_invalid_dh_prime_length() -> None:
    with pytest.raises(DhError, match="dh_prime length"):
        make_dh_result(g=3, dh_prime=_DH_PRIME[:-1], g_a=_SAFE_GA)


def test_make_dh_result__accepts_known_telegram_prime_without_probable_prime_check(
    monkeypatch,
) -> None:
    def fail_if_called(_p: int) -> bool:
        raise AssertionError("known Telegram prime must use the compatibility fast path")

    monkeypatch.setattr(dh, "_is_safe_prime", fail_if_called)
    p, ga = dh._validate_dh_params(g=3, dh_prime=_DH_PRIME, g_a=_SAFE_GA)
    assert p == _P
    assert ga == _LOW


def test_validate_dh_params__checks_unknown_prime_and_sophie_germain_factor(monkeypatch) -> None:
    unknown_p = _P - 2
    calls: list[int] = []

    def probable_prime(n: int, *, rounds: int = 64) -> bool:
        assert rounds == 64
        calls.append(n)
        return True

    dh._is_safe_prime.cache_clear()
    monkeypatch.setattr(dh, "_is_probable_prime", probable_prime)

    p, ga = dh._validate_dh_params(
        g=4,
        dh_prime=unknown_p.to_bytes(256, "big"),
        g_a=_SAFE_GA,
    )

    assert (p, ga) == (unknown_p, _LOW)
    assert calls == [unknown_p, (unknown_p - 1) // 2]


def test_validate_dh_params__rejects_unknown_non_safe_prime(monkeypatch) -> None:
    unknown_p = _P - 4

    def only_p_is_prime(n: int, *, rounds: int = 64) -> bool:
        assert rounds == 64
        return n == unknown_p

    dh._is_safe_prime.cache_clear()
    monkeypatch.setattr(dh, "_is_probable_prime", only_p_is_prime)

    with pytest.raises(DhError, match="not a safe prime"):
        dh._validate_dh_params(
            g=4,
            dh_prime=unknown_p.to_bytes(256, "big"),
            g_a=_SAFE_GA,
        )


def test_validate_dh_params__rejects_obvious_composite_prime() -> None:
    composite = (1 << 2048) - 1  # divisible by 3
    dh._is_safe_prime.cache_clear()

    with pytest.raises(DhError, match="not a safe prime"):
        dh._validate_dh_params(
            g=4,
            dh_prime=composite.to_bytes(256, "big"),
            g_a=_SAFE_GA,
        )


def test_validate_dh_params__rejects_generator_incompatible_with_prime() -> None:
    with pytest.raises(DhError, match="incompatible"):
        dh._validate_dh_params(g=2, dh_prime=_DH_PRIME, g_a=_SAFE_GA)


def test_make_dh_result__rejects_unsafe_g_a() -> None:
    with pytest.raises(DhError, match="unsafe g_a"):
        make_dh_result(g=3, dh_prime=_DH_PRIME, g_a=(2).to_bytes(256, "big"))


def test_make_dh_result__rejects_unsafe_g_b(monkeypatch) -> None:
    def fake_pow(base: int, exp: int, mod: int) -> int:
        _ = base, exp, mod
        return 2

    monkeypatch.setattr(dh, "random_bytes", lambda _n: _random_b(123456789))
    monkeypatch.setattr(dh, "pow", fake_pow, raising=False)

    with pytest.raises(DhError, match="g_b"):
        make_dh_result(g=3, dh_prime=_DH_PRIME, g_a=_SAFE_GA)
