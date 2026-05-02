from __future__ import annotations

import pytest

from telecraft.mtproto.auth import dh
from telecraft.mtproto.auth.dh import DhError, auth_key_id, make_dh_result

_P = (1 << 2048) - 159
_DH_PRIME = _P.to_bytes(256, "big", signed=False)
_LOW = 1 << (2048 - 64)
_SAFE_GA = _LOW.to_bytes(256, "big", signed=False)


def _random_b(value: int) -> bytes:
    return value.to_bytes(256, "big", signed=False)


def test_make_dh_result_basic(monkeypatch) -> None:
    monkeypatch.setattr(dh, "random_bytes", lambda _n: _random_b(1984))

    res = make_dh_result(g=5, dh_prime=_DH_PRIME, g_a=_SAFE_GA)
    assert isinstance(res.auth_key, (bytes, bytearray))
    assert len(res.auth_key) == 256
    assert len(res.auth_key_id) == 8
    assert isinstance(res.g_b, (bytes, bytearray))
    assert len(res.g_b) == 256


def test_make_dh_result__pads_leading_zero_auth_key_and_hashes_padded(monkeypatch) -> None:
    def fake_pow(base: int, exp: int, mod: int) -> int:
        _ = exp, mod
        if base == 5:
            return _LOW
        return 1

    monkeypatch.setattr(dh, "random_bytes", lambda _n: _random_b(123456789))
    monkeypatch.setattr(dh, "pow", fake_pow, raising=False)

    res = make_dh_result(g=5, dh_prime=_DH_PRIME, g_a=_SAFE_GA)

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
        make_dh_result(g=5, dh_prime=_DH_PRIME[:-1], g_a=_SAFE_GA)


def test_make_dh_result__rejects_unsafe_g_a() -> None:
    with pytest.raises(DhError, match="unsafe g_a"):
        make_dh_result(g=5, dh_prime=_DH_PRIME, g_a=(2).to_bytes(256, "big"))


def test_make_dh_result__rejects_unsafe_g_b(monkeypatch) -> None:
    def fake_pow(base: int, exp: int, mod: int) -> int:
        _ = base, exp, mod
        return 2

    monkeypatch.setattr(dh, "random_bytes", lambda _n: _random_b(123456789))
    monkeypatch.setattr(dh, "pow", fake_pow, raising=False)

    with pytest.raises(DhError, match="g_b"):
        make_dh_result(g=5, dh_prime=_DH_PRIME, g_a=_SAFE_GA)
