from __future__ import annotations

from telecraft.client import AuthSessionRef, CdnFileRef, FileLocationRef, LoginTokenRef
from telecraft.client.auth import build_import_authorization, build_login_token
from telecraft.client.uploads import build_cdn_file_token, build_file_location


def test_ref_builders__login_token_ref_from_bytes__returns_expected_shape() -> None:
    ref = LoginTokenRef.from_bytes(b"abc")
    assert ref.to_bytes() == b"abc"


def test_ref_builders__auth_session_ref_from_parts__returns_expected_shape() -> None:
    ref = AuthSessionRef.from_parts(2, 11, b"payload")
    assert ref.dc_id == 2 and ref.auth_id == 11 and ref.payload == b"payload"


def test_ref_builders__build_import_authorization__returns_expected_shape() -> None:
    auth_id, payload = build_import_authorization(AuthSessionRef.from_parts(4, 9, b"x"))
    assert auth_id == 9 and payload == b"x"


def test_ref_builders__file_location_ref_document__returns_expected_shape() -> None:
    ref = FileLocationRef.document(id=1, access_hash=2, file_reference=b"r", thumb_size="x")
    out = build_file_location(ref)
    assert getattr(out, "TL_NAME", "") == "inputDocumentFileLocation"


def test_ref_builders__cdn_file_ref_from_hex__returns_expected_shape() -> None:
    ref = CdnFileRef.from_hex("616263")
    assert build_cdn_file_token(ref) == b"abc"


def test_ref_builders__build_login_token__returns_expected_shape() -> None:
    out = build_login_token(LoginTokenRef.from_bytes(b"z"))
    assert out == b"z"
