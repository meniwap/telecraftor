from __future__ import annotations

from collections.abc import Sequence
from secrets import randbits
from typing import TYPE_CHECKING, Any

from telecraft.client.apis._utils import resolve_input_peer, resolve_input_user
from telecraft.client.calls import (
    CallParticipantRef,
    GroupCallJoinParams,
    GroupCallRef,
    JoinAsRef,
    PhoneCallRef,
    build_data_json,
    build_input_group_call,
    build_input_phone_call,
)
from telecraft.client.peers import PeerRef
from telecraft.tl.generated.functions import (
    PhoneAcceptCall,
    PhoneConfirmCall,
    PhoneCreateConferenceCall,
    PhoneCreateGroupCall,
    PhoneDeclineConferenceCallInvite,
    PhoneDeleteConferenceCallParticipants,
    PhoneDiscardCall,
    PhoneDiscardGroupCall,
    PhoneEditGroupCallParticipant,
    PhoneEditGroupCallTitle,
    PhoneExportGroupCallInvite,
    PhoneGetGroupCall,
    PhoneGetGroupCallChainBlocks,
    PhoneGetGroupCallStreamRtmpUrl,
    PhoneGetGroupParticipants,
    PhoneInviteConferenceCallParticipant,
    PhoneInviteToGroupCall,
    PhoneJoinGroupCall,
    PhoneJoinGroupCallPresentation,
    PhoneLeaveGroupCall,
    PhoneLeaveGroupCallPresentation,
    PhoneSendConferenceCallBroadcast,
    PhoneToggleGroupCallRecord,
    PhoneToggleGroupCallSettings,
)
from telecraft.tl.generated.types import PhoneCallProtocol

if TYPE_CHECKING:
    from telecraft.client.mtproto import MtprotoClient


def _default_protocol() -> PhoneCallProtocol:
    return PhoneCallProtocol(
        flags=0,
        udp_p2p=True,
        udp_reflector=True,
        min_layer=0,
        max_layer=0,
        library_versions=[],
    )


async def _to_call_ref(ref: GroupCallRef | Any) -> Any:
    return build_input_group_call(ref)


async def _to_phone_call_ref(ref: PhoneCallRef | Any) -> Any:
    return build_input_phone_call(ref)


async def _to_join_as(
    raw: MtprotoClient,
    join_as: JoinAsRef | PeerRef | Any,
    *,
    timeout: float,
) -> Any:
    if isinstance(join_as, JoinAsRef):
        return await resolve_input_peer(raw, join_as.peer, timeout=timeout)
    if isinstance(join_as, (str, tuple)):
        return await resolve_input_peer(raw, join_as, timeout=timeout)
    return join_as


async def _to_participant(
    raw: MtprotoClient,
    participant: CallParticipantRef | PeerRef | Any,
    *,
    timeout: float,
) -> Any:
    if isinstance(participant, CallParticipantRef):
        return await resolve_input_peer(raw, participant.peer, timeout=timeout)
    if isinstance(participant, (str, tuple)):
        return await resolve_input_peer(raw, participant, timeout=timeout)
    return participant


class CallsGroupChainAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def blocks(
        self,
        call_ref: GroupCallRef | Any,
        sub_chain_id: int,
        *,
        offset: int = 0,
        limit: int = 100,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            PhoneGetGroupCallChainBlocks(
                call=await _to_call_ref(call_ref),
                sub_chain_id=int(sub_chain_id),
                offset=int(offset),
                limit=int(limit),
            ),
            timeout=timeout,
        )


class CallsGroupAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw
        self.chain = CallsGroupChainAPI(raw)

    async def create(
        self,
        peer: PeerRef,
        *,
        title: str | None = None,
        schedule_date: int | None = None,
        rtmp_stream: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        flags = 0
        if rtmp_stream:
            flags |= 4
        if title is not None:
            flags |= 1
        if schedule_date is not None:
            flags |= 2
        return await self._raw.invoke_api(
            PhoneCreateGroupCall(
                flags=flags,
                rtmp_stream=True if rtmp_stream else None,
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                random_id=randbits(31),
                title=str(title) if title is not None else None,
                schedule_date=int(schedule_date) if schedule_date is not None else None,
            ),
            timeout=timeout,
        )

    async def get(
        self,
        call_ref: GroupCallRef | Any,
        *,
        limit: int = 100,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            PhoneGetGroupCall(call=await _to_call_ref(call_ref), limit=int(limit)),
            timeout=timeout,
        )

    async def participants(
        self,
        call_ref: GroupCallRef | Any,
        *,
        ids: Sequence[CallParticipantRef | PeerRef | Any] = (),
        sources: Sequence[int] = (),
        offset: str = "",
        limit: int = 100,
        timeout: float = 20.0,
    ) -> Any:
        payload_ids = [
            await _to_participant(self._raw, participant, timeout=timeout) for participant in ids
        ]
        return await self._raw.invoke_api(
            PhoneGetGroupParticipants(
                call=await _to_call_ref(call_ref),
                ids=payload_ids,
                sources=[int(source) for source in sources],
                offset=str(offset),
                limit=int(limit),
            ),
            timeout=timeout,
        )

    async def join(
        self,
        call_ref: GroupCallRef | Any,
        join_as: JoinAsRef | PeerRef | Any,
        params: GroupCallJoinParams | dict[str, Any] | str | Any,
        *,
        muted: bool = False,
        video_stopped: bool = True,
        invite_hash: str | None = None,
        timeout: float = 20.0,
    ) -> Any:
        flags = 0
        if muted:
            flags |= 1
        if invite_hash is not None:
            flags |= 2
        if video_stopped:
            flags |= 4
        return await self._raw.invoke_api(
            PhoneJoinGroupCall(
                flags=flags,
                muted=True if muted else None,
                video_stopped=True if video_stopped else None,
                call=await _to_call_ref(call_ref),
                join_as=await _to_join_as(self._raw, join_as, timeout=timeout),
                invite_hash=str(invite_hash) if invite_hash is not None else None,
                public_key=b"",
                block=b"",
                params=build_data_json(params),
            ),
            timeout=timeout,
        )

    async def leave(
        self,
        call_ref: GroupCallRef | Any,
        *,
        source: int | None = None,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            PhoneLeaveGroupCall(
                call=await _to_call_ref(call_ref),
                source=int(source) if source is not None else 0,
            ),
            timeout=timeout,
        )

    async def invite(
        self,
        call_ref: GroupCallRef | Any,
        users: Sequence[PeerRef],
        *,
        timeout: float = 20.0,
    ) -> Any:
        payload_users = [
            await resolve_input_user(self._raw, user, timeout=timeout) for user in users
        ]
        return await self._raw.invoke_api(
            PhoneInviteToGroupCall(call=await _to_call_ref(call_ref), users=payload_users),
            timeout=timeout,
        )

    async def edit_participant(
        self,
        call_ref: GroupCallRef | Any,
        participant: CallParticipantRef | PeerRef | Any,
        *,
        muted: bool | None = None,
        volume: int | None = None,
        raise_hand: bool | None = None,
        video_stopped: bool | None = None,
        timeout: float = 20.0,
    ) -> Any:
        flags = 0
        if muted is not None:
            flags |= 1
        if volume is not None:
            flags |= 2
        if raise_hand is not None:
            flags |= 4
        if video_stopped is not None:
            flags |= 8
        return await self._raw.invoke_api(
            PhoneEditGroupCallParticipant(
                flags=flags,
                call=await _to_call_ref(call_ref),
                participant=await _to_participant(self._raw, participant, timeout=timeout),
                muted=bool(muted) if muted is not None else None,
                volume=int(volume) if volume is not None else None,
                raise_hand=bool(raise_hand) if raise_hand is not None else None,
                video_stopped=bool(video_stopped) if video_stopped is not None else None,
                video_paused=None,
                presentation_paused=None,
            ),
            timeout=timeout,
        )

    async def toggle_record(
        self,
        call_ref: GroupCallRef | Any,
        start: bool,
        *,
        title: str | None = None,
        video: bool = False,
        video_portrait: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        flags = 0
        if video:
            flags |= 2
        if title is not None:
            flags |= 4
        if video_portrait:
            flags |= 8
        return await self._raw.invoke_api(
            PhoneToggleGroupCallRecord(
                flags=flags,
                start=bool(start),
                video=True if video else None,
                call=await _to_call_ref(call_ref),
                title=str(title) if title is not None else None,
                video_portrait=True if video_portrait else None,
            ),
            timeout=timeout,
        )

    async def edit_title(
        self,
        call_ref: GroupCallRef | Any,
        title: str,
        *,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            PhoneEditGroupCallTitle(call=await _to_call_ref(call_ref), title=str(title)),
            timeout=timeout,
        )

    async def export_invite(
        self,
        call_ref: GroupCallRef | Any,
        *,
        can_self_unmute: bool | None = None,
        timeout: float = 20.0,
    ) -> Any:
        flags = 1 if can_self_unmute is not None else 0
        return await self._raw.invoke_api(
            PhoneExportGroupCallInvite(
                flags=flags,
                can_self_unmute=bool(can_self_unmute) if can_self_unmute is not None else None,
                call=await _to_call_ref(call_ref),
            ),
            timeout=timeout,
        )

    async def toggle_settings(
        self,
        call_ref: GroupCallRef | Any,
        *,
        join_muted: bool | None = None,
        reset_invite_hash: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        flags = 0
        if join_muted is not None:
            flags |= 1
        if reset_invite_hash:
            flags |= 2
        return await self._raw.invoke_api(
            PhoneToggleGroupCallSettings(
                flags=flags,
                reset_invite_hash=True if reset_invite_hash else None,
                call=await _to_call_ref(call_ref),
                join_muted=bool(join_muted) if join_muted is not None else None,
                messages_enabled=None,
                send_paid_messages_stars=None,
            ),
            timeout=timeout,
        )

    async def discard(self, call_ref: GroupCallRef | Any, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            PhoneDiscardGroupCall(call=await _to_call_ref(call_ref)),
            timeout=timeout,
        )

    async def mute(
        self,
        call_ref: GroupCallRef | Any,
        participant: CallParticipantRef | PeerRef | Any,
        *,
        timeout: float = 20.0,
    ) -> Any:
        return await self.edit_participant(
            call_ref,
            participant,
            muted=True,
            timeout=timeout,
        )

    async def unmute(
        self,
        call_ref: GroupCallRef | Any,
        participant: CallParticipantRef | PeerRef | Any,
        *,
        timeout: float = 20.0,
    ) -> Any:
        return await self.edit_participant(
            call_ref,
            participant,
            muted=False,
            timeout=timeout,
        )

    async def raise_hand(
        self,
        call_ref: GroupCallRef | Any,
        participant: CallParticipantRef | PeerRef | Any,
        *,
        timeout: float = 20.0,
    ) -> Any:
        return await self.edit_participant(
            call_ref,
            participant,
            raise_hand=True,
            timeout=timeout,
        )

    async def lower_hand(
        self,
        call_ref: GroupCallRef | Any,
        participant: CallParticipantRef | PeerRef | Any,
        *,
        timeout: float = 20.0,
    ) -> Any:
        return await self.edit_participant(
            call_ref,
            participant,
            raise_hand=False,
            timeout=timeout,
        )

    async def set_volume(
        self,
        call_ref: GroupCallRef | Any,
        participant: CallParticipantRef | PeerRef | Any,
        volume: int,
        *,
        timeout: float = 20.0,
    ) -> Any:
        return await self.edit_participant(
            call_ref,
            participant,
            volume=int(volume),
            timeout=timeout,
        )

    async def start_recording(
        self,
        call_ref: GroupCallRef | Any,
        *,
        title: str | None = None,
        timeout: float = 20.0,
    ) -> Any:
        return await self.toggle_record(call_ref, True, title=title, timeout=timeout)

    async def stop_recording(self, call_ref: GroupCallRef | Any, *, timeout: float = 20.0) -> Any:
        return await self.toggle_record(call_ref, False, timeout=timeout)


class CallsStreamAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def rtmp_url(
        self,
        peer: PeerRef,
        *,
        revoke: bool = False,
        live_story: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        flags = 0
        if revoke:
            flags |= 1
        if live_story:
            flags |= 2
        return await self._raw.invoke_api(
            PhoneGetGroupCallStreamRtmpUrl(
                flags=flags,
                live_story=True if live_story else None,
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                revoke=bool(revoke),
            ),
            timeout=timeout,
        )

    async def join_presentation(
        self,
        call_ref: GroupCallRef | Any,
        params: GroupCallJoinParams | dict[str, Any] | str | Any,
        *,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            PhoneJoinGroupCallPresentation(
                call=await _to_call_ref(call_ref),
                params=build_data_json(params),
            ),
            timeout=timeout,
        )

    async def leave_presentation(
        self,
        call_ref: GroupCallRef | Any,
        *,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            PhoneLeaveGroupCallPresentation(call=await _to_call_ref(call_ref)),
            timeout=timeout,
        )

    async def rtmp_url_revoke(self, peer: PeerRef, *, timeout: float = 20.0) -> Any:
        return await self.rtmp_url(peer, revoke=True, timeout=timeout)


class CallsConferenceAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def create(
        self,
        peer: PeerRef,
        random_id: int,
        *,
        params: GroupCallJoinParams | dict[str, Any] | str | Any = "{}",
        muted: bool = False,
        video_stopped: bool = True,
        timeout: float = 20.0,
    ) -> Any:
        flags = 0
        if muted:
            flags |= 1
        if video_stopped:
            flags |= 2
        return await self._raw.invoke_api(
            PhoneCreateConferenceCall(
                flags=flags,
                muted=True if muted else None,
                video_stopped=True if video_stopped else None,
                join=await resolve_input_peer(self._raw, peer, timeout=timeout),
                random_id=int(random_id),
                public_key=b"",
                block=b"",
                params=build_data_json(params),
            ),
            timeout=timeout,
        )

    async def accept(
        self,
        call_ref: PhoneCallRef | Any,
        *,
        g_b: bytes = b"",
        protocol: Any | None = None,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            PhoneAcceptCall(
                peer=await _to_phone_call_ref(call_ref),
                g_b=bytes(g_b),
                protocol=protocol if protocol is not None else _default_protocol(),
            ),
            timeout=timeout,
        )

    async def confirm(
        self,
        call_ref: PhoneCallRef | Any,
        key_fingerprint: int,
        *,
        g_a: bytes = b"",
        protocol: Any | None = None,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            PhoneConfirmCall(
                peer=await _to_phone_call_ref(call_ref),
                g_a=bytes(g_a),
                key_fingerprint=int(key_fingerprint),
                protocol=protocol if protocol is not None else _default_protocol(),
            ),
            timeout=timeout,
        )

    async def discard(
        self,
        call_ref: PhoneCallRef | Any,
        *,
        reason: Any | None = None,
        duration: int = 0,
        connection_id: int = 0,
        video: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        flags = 1 if video else 0
        return await self._raw.invoke_api(
            PhoneDiscardCall(
                flags=flags,
                video=True if video else None,
                peer=await _to_phone_call_ref(call_ref),
                duration=int(duration),
                reason=reason,
                connection_id=int(connection_id),
            ),
            timeout=timeout,
        )

    async def delete_participants(
        self,
        call_ref: GroupCallRef | Any,
        ids: Sequence[int],
        block: bytes | bytearray,
        *,
        only_left: bool = False,
        kick: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        flags = 0
        if only_left:
            flags |= 1
        if kick:
            flags |= 2
        return await self._raw.invoke_api(
            PhoneDeleteConferenceCallParticipants(
                flags=flags,
                only_left=True if only_left else None,
                kick=True if kick else None,
                call=await _to_call_ref(call_ref),
                ids=[int(item) for item in ids],
                block=bytes(block),
            ),
            timeout=timeout,
        )

    async def broadcast(
        self,
        call_ref: GroupCallRef | Any,
        block: bytes | bytearray,
        *,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            PhoneSendConferenceCallBroadcast(
                call=await _to_call_ref(call_ref),
                block=bytes(block),
            ),
            timeout=timeout,
        )

    async def invite(
        self,
        call_ref: GroupCallRef | Any,
        user: PeerRef,
        *,
        video: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        flags = 1 if video else 0
        return await self._raw.invoke_api(
            PhoneInviteConferenceCallParticipant(
                flags=flags,
                video=True if video else None,
                call=await _to_call_ref(call_ref),
                user_id=await resolve_input_user(self._raw, user, timeout=timeout),
            ),
            timeout=timeout,
        )

    async def decline_invite(self, msg_id: int, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            PhoneDeclineConferenceCallInvite(msg_id=int(msg_id)),
            timeout=timeout,
        )

    async def reject(self, call_ref: PhoneCallRef | Any, *, timeout: float = 20.0) -> Any:
        return await self.discard(call_ref, timeout=timeout)


class CallsAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw
        self.group = CallsGroupAPI(raw)
        self.stream = CallsStreamAPI(raw)
        self.conference = CallsConferenceAPI(raw)
