from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from telecraft.tl.generated.types import InputPasskeyCredentialPublicKey


@dataclass(frozen=True, slots=True)
class PasskeyRef:
    passkey_id: str

    @classmethod
    def from_id(cls, passkey_id: str) -> PasskeyRef:
        value = str(passkey_id).strip()
        if not value:
            raise ValueError("passkey_id cannot be empty")
        return cls(passkey_id=value)


@dataclass(frozen=True, slots=True)
class PasskeyCredential:
    credential_id: str
    raw_id: str
    response: Any

    @classmethod
    def public_key(
        cls,
        credential_id: str,
        raw_id: str,
        response: Any,
    ) -> PasskeyCredential:
        cid = str(credential_id).strip()
        rid = str(raw_id).strip()
        if not cid:
            raise ValueError("credential_id cannot be empty")
        if not rid:
            raise ValueError("raw_id cannot be empty")
        return cls(credential_id=cid, raw_id=rid, response=response)


def build_passkey_id(value: PasskeyRef | str) -> str:
    if isinstance(value, PasskeyRef):
        return str(value.passkey_id)
    normalized = str(value).strip()
    if not normalized:
        raise ValueError("passkey_id cannot be empty")
    return normalized


def build_input_passkey_credential(value: PasskeyCredential | Any) -> Any:
    if not isinstance(value, PasskeyCredential):
        return value
    return InputPasskeyCredentialPublicKey(
        id=str(value.credential_id),
        raw_id=str(value.raw_id),
        response=value.response,
    )
