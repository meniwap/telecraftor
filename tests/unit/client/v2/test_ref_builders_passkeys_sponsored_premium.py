from __future__ import annotations

import pytest

from telecraft.client import PremiumBoostSlots
from telecraft.client.passkeys import (
    PasskeyCredential,
    PasskeyRef,
    build_input_passkey_credential,
    build_passkey_id,
)
from telecraft.client.premium import build_premium_slots
from telecraft.client.sponsored import (
    SponsoredMessageRef,
    SponsoredReportOption,
    build_sponsored_option,
    build_sponsored_random_id,
)


@pytest.mark.unit
def test_ref_builders_passkeys__build_passkey_id__normalizes() -> None:
    ref = PasskeyRef.from_id("abc")
    assert build_passkey_id(ref) == "abc"
    assert build_passkey_id("  xyz ") == "xyz"


@pytest.mark.unit
def test_ref_builders_passkeys__build_credential__returns_input() -> None:
    credential = PasskeyCredential.public_key("id", "raw", object())
    out = build_input_passkey_credential(credential)
    assert getattr(out, "TL_NAME", "") == "inputPasskeyCredentialPublicKey"


@pytest.mark.unit
def test_ref_builders_sponsored__random_id_and_option__converted() -> None:
    rid = SponsoredMessageRef.from_hex("0102")
    assert build_sponsored_random_id(rid) == b"\x01\x02"
    assert build_sponsored_random_id("0102") == b"\x01\x02"

    opt = SponsoredReportOption.from_text("spam")
    assert build_sponsored_option(opt) == b"spam"
    assert build_sponsored_option("ab") == b"ab"


@pytest.mark.unit
def test_ref_builders_premium__slots__converted() -> None:
    slots = PremiumBoostSlots.of(1, 2, 3)
    assert build_premium_slots(slots) == [1, 2, 3]
    assert build_premium_slots([4, 5]) == [4, 5]
