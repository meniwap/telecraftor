from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class LoginTokenRef:
    token: bytes

    @classmethod
    def from_bytes(cls, token: bytes | bytearray) -> LoginTokenRef:
        return cls(token=bytes(token))

    @classmethod
    def from_base64(cls, token_b64: str) -> LoginTokenRef:
        raw = base64.b64decode(str(token_b64).encode("ascii"))
        return cls(token=bytes(raw))

    @classmethod
    def from_hex(cls, token_hex: str) -> LoginTokenRef:
        return cls(token=bytes.fromhex(str(token_hex)))

    def to_bytes(self) -> bytes:
        return bytes(self.token)

    def to_base64(self) -> str:
        return base64.b64encode(self.token).decode("ascii")


@dataclass(frozen=True, slots=True)
class AuthSessionRef:
    dc_id: int
    auth_id: int
    payload: bytes

    @classmethod
    def from_parts(cls, dc_id: int, auth_id: int, payload: bytes | bytearray) -> AuthSessionRef:
        return cls(dc_id=int(dc_id), auth_id=int(auth_id), payload=bytes(payload))


def build_login_token(token_or_ref: LoginTokenRef | Any) -> Any:
    if isinstance(token_or_ref, LoginTokenRef):
        return token_or_ref.to_bytes()
    if isinstance(token_or_ref, bytearray):
        return bytes(token_or_ref)
    if isinstance(token_or_ref, bytes):
        return token_or_ref
    if isinstance(token_or_ref, str):
        return token_or_ref.encode("utf-8")
    return token_or_ref


def build_import_authorization(
    id_or_ref: AuthSessionRef | Any,
    payload: Any | None = None,
) -> tuple[int, Any]:
    if isinstance(id_or_ref, AuthSessionRef):
        return int(id_or_ref.auth_id), bytes(id_or_ref.payload)
    if isinstance(id_or_ref, tuple) and len(id_or_ref) == 2:
        auth_id, raw = id_or_ref
        return int(auth_id), raw
    if isinstance(id_or_ref, dict) and {"id", "bytes"}.issubset(id_or_ref):
        return int(id_or_ref["id"]), id_or_ref["bytes"]
    return int(id_or_ref), payload
