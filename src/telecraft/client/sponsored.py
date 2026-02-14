from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class SponsoredMessageRef:
    random_id: bytes

    @classmethod
    def from_bytes(cls, random_id: bytes | bytearray) -> SponsoredMessageRef:
        return cls(random_id=bytes(random_id))

    @classmethod
    def from_hex(cls, random_id_hex: str) -> SponsoredMessageRef:
        value = str(random_id_hex).strip().lower()
        if value.startswith("0x"):
            value = value[2:]
        if not value:
            raise ValueError("random_id_hex cannot be empty")
        return cls(random_id=bytes.fromhex(value))


@dataclass(frozen=True, slots=True)
class SponsoredReportOption:
    option: bytes

    @classmethod
    def from_bytes(cls, option: bytes | bytearray) -> SponsoredReportOption:
        return cls(option=bytes(option))

    @classmethod
    def from_text(cls, option: str) -> SponsoredReportOption:
        return cls(option=str(option).encode("utf-8"))


def build_sponsored_random_id(value: SponsoredMessageRef | bytes | bytearray | str | Any) -> Any:
    if isinstance(value, SponsoredMessageRef):
        return bytes(value.random_id)
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("0x"):
            text = text[2:]
        if text and all(ch in "0123456789abcdefABCDEF" for ch in text) and len(text) % 2 == 0:
            try:
                return bytes.fromhex(text)
            except ValueError:
                return value.encode("utf-8")
        return value.encode("utf-8")
    return value


def build_sponsored_option(value: SponsoredReportOption | bytes | bytearray | str | Any) -> Any:
    if isinstance(value, SponsoredReportOption):
        return bytes(value.option)
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    if isinstance(value, str):
        return value.encode("utf-8")
    return value
