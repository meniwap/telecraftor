from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TakeoutScopes:
    contacts: bool = True
    message_users: bool = True
    message_chats: bool = True
    message_megagroups: bool = True
    message_channels: bool = True
    files: bool = True


@dataclass(frozen=True, slots=True)
class TakeoutSessionRef:
    takeout_id: int

    @classmethod
    def from_id(cls, takeout_id: int) -> TakeoutSessionRef:
        return cls(takeout_id=int(takeout_id))


def build_takeout_flags(scopes: TakeoutScopes) -> int:
    flags = 0
    if scopes.contacts:
        flags |= 1
    if scopes.message_users:
        flags |= 2
    if scopes.message_chats:
        flags |= 4
    if scopes.message_megagroups:
        flags |= 8
    if scopes.message_channels:
        flags |= 16
    if scopes.files:
        flags |= 32
    return flags
