from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from telecraft.client.peers import PeerRef
from telecraft.tl.generated.types import DataJson, InputGroupCall, InputPhoneCall


@dataclass(frozen=True, slots=True)
class GroupCallRef:
    call_id: int
    access_hash: int

    @classmethod
    def from_parts(cls, call_id: int, access_hash: int) -> GroupCallRef:
        return cls(call_id=int(call_id), access_hash=int(access_hash))


@dataclass(frozen=True, slots=True)
class PhoneCallRef:
    call_id: int
    access_hash: int

    @classmethod
    def from_parts(cls, call_id: int, access_hash: int) -> PhoneCallRef:
        return cls(call_id=int(call_id), access_hash=int(access_hash))


@dataclass(frozen=True, slots=True)
class JoinAsRef:
    peer: PeerRef

    @classmethod
    def peer_ref(cls, peer: PeerRef) -> JoinAsRef:
        return cls(peer=peer)


@dataclass(frozen=True, slots=True)
class CallParticipantRef:
    peer: PeerRef

    @classmethod
    def peer_ref(cls, peer: PeerRef) -> CallParticipantRef:
        return cls(peer=peer)


@dataclass(frozen=True, slots=True)
class GroupCallJoinParams:
    data: str

    @classmethod
    def from_json(cls, raw_json: str) -> GroupCallJoinParams:
        value = str(raw_json).strip()
        if not value:
            raise ValueError("raw_json cannot be empty")
        return cls(data=value)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> GroupCallJoinParams:
        return cls(data=json.dumps(payload, separators=(",", ":"), ensure_ascii=False))


def build_input_group_call(ref: GroupCallRef | Any) -> Any:
    if not isinstance(ref, GroupCallRef):
        return ref
    return InputGroupCall(id=int(ref.call_id), access_hash=int(ref.access_hash))


def build_input_phone_call(ref: PhoneCallRef | Any) -> Any:
    if not isinstance(ref, PhoneCallRef):
        return ref
    return InputPhoneCall(id=int(ref.call_id), access_hash=int(ref.access_hash))


def build_data_json(params: GroupCallJoinParams | dict[str, Any] | str | Any) -> Any:
    if isinstance(params, GroupCallJoinParams):
        return DataJson(data=str(params.data))
    if isinstance(params, dict):
        return DataJson(data=json.dumps(params, separators=(",", ":"), ensure_ascii=False))
    if isinstance(params, str):
        return DataJson(data=params)
    return params
