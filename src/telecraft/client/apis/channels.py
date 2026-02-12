from __future__ import annotations

from typing import TYPE_CHECKING, Any

from telecraft.client.apis._utils import resolve_input_channel, resolve_input_peer
from telecraft.client.peers import PeerRef
from telecraft.client.stickers import StickerSetRef, build_input_sticker_set
from telecraft.tl.generated.functions import (
    ChannelsDeleteHistory,
    ChannelsDeleteParticipantHistory,
    ChannelsExportMessageLink,
    ChannelsGetAdminLog,
    ChannelsReadHistory,
    ChannelsReorderUsernames,
    ChannelsReportAntiSpamFalsePositive,
    ChannelsSetBoostsToUnblockRestrictions,
    ChannelsSetDiscussionGroup,
    ChannelsSetEmojiStickers,
    ChannelsSetStickers,
    ChannelsToggleAntiSpam,
    ChannelsToggleParticipantsHidden,
    ChannelsTogglePreHistoryHidden,
    ChannelsToggleSignatures,
    ChannelsToggleSlowMode,
    ChannelsUpdateColor,
    ChannelsUpdateEmojiStatus,
    ChannelsUpdateUsername,
)

if TYPE_CHECKING:
    from telecraft.client.mtproto import MtprotoClient


class ChannelSettingsAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def set_stickers(
        self,
        channel: PeerRef,
        sticker_set: StickerSetRef | Any,
        *,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            ChannelsSetStickers(
                channel=await resolve_input_channel(self._raw, channel, timeout=timeout),
                stickerset=build_input_sticker_set(sticker_set),
            ),
            timeout=timeout,
        )

    async def set_emoji_stickers(
        self,
        channel: PeerRef,
        sticker_set: StickerSetRef | Any,
        *,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            ChannelsSetEmojiStickers(
                channel=await resolve_input_channel(self._raw, channel, timeout=timeout),
                stickerset=build_input_sticker_set(sticker_set),
            ),
            timeout=timeout,
        )

    async def toggle_antispam(
        self, channel: PeerRef, enabled: bool, *, timeout: float = 20.0
    ) -> Any:
        return await self._raw.invoke_api(
            ChannelsToggleAntiSpam(
                channel=await resolve_input_channel(self._raw, channel, timeout=timeout),
                enabled=bool(enabled),
            ),
            timeout=timeout,
        )

    async def report_antispam_false_positive(
        self,
        channel: PeerRef,
        msg_id: int,
        *,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            ChannelsReportAntiSpamFalsePositive(
                channel=await resolve_input_channel(self._raw, channel, timeout=timeout),
                msg_id=int(msg_id),
            ),
            timeout=timeout,
        )

    async def toggle_participants_hidden(
        self,
        channel: PeerRef,
        enabled: bool,
        *,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            ChannelsToggleParticipantsHidden(
                channel=await resolve_input_channel(self._raw, channel, timeout=timeout),
                enabled=bool(enabled),
            ),
            timeout=timeout,
        )

    async def update_color(
        self,
        channel: PeerRef,
        *,
        color: int | None = None,
        background_emoji_id: int | None = None,
        for_profile: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        flags = 0
        if background_emoji_id is not None:
            flags |= 1
        if for_profile:
            flags |= 2
        if color is not None:
            flags |= 4
        return await self._raw.invoke_api(
            ChannelsUpdateColor(
                flags=flags,
                for_profile=True if for_profile else None,
                channel=await resolve_input_channel(self._raw, channel, timeout=timeout),
                color=int(color) if color is not None else None,
                background_emoji_id=(
                    int(background_emoji_id) if background_emoji_id is not None else None
                ),
            ),
            timeout=timeout,
        )

    async def update_emoji_status(
        self,
        channel: PeerRef,
        emoji_status: Any,
        *,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            ChannelsUpdateEmojiStatus(
                channel=await resolve_input_channel(self._raw, channel, timeout=timeout),
                emoji_status=emoji_status,
            ),
            timeout=timeout,
        )

    async def set_boosts_to_unblock(
        self,
        channel: PeerRef,
        boosts: int,
        *,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            ChannelsSetBoostsToUnblockRestrictions(
                channel=await resolve_input_channel(self._raw, channel, timeout=timeout),
                boosts=int(boosts),
            ),
            timeout=timeout,
        )

    async def toggle_signatures(
        self,
        channel: PeerRef,
        enabled: bool = True,
        *,
        profiles_enabled: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        flags = 1 if profiles_enabled else 0
        return await self._raw.invoke_api(
            ChannelsToggleSignatures(
                flags=flags,
                signatures_enabled=bool(enabled),
                profiles_enabled=True if profiles_enabled else None,
                channel=await resolve_input_channel(self._raw, channel, timeout=timeout),
            ),
            timeout=timeout,
        )

    async def toggle_prehistory_hidden(
        self,
        channel: PeerRef,
        enabled: bool,
        *,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            ChannelsTogglePreHistoryHidden(
                channel=await resolve_input_channel(self._raw, channel, timeout=timeout),
                enabled=bool(enabled),
            ),
            timeout=timeout,
        )

    async def set_discussion_group(
        self,
        channel: PeerRef,
        group: PeerRef,
        *,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            ChannelsSetDiscussionGroup(
                broadcast=await resolve_input_channel(self._raw, channel, timeout=timeout),
                group=await resolve_input_channel(self._raw, group, timeout=timeout),
            ),
            timeout=timeout,
        )

    async def update_username(
        self,
        channel: PeerRef,
        username: str = "",
        *,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            ChannelsUpdateUsername(
                channel=await resolve_input_channel(self._raw, channel, timeout=timeout),
                username=str(username),
            ),
            timeout=timeout,
        )

    async def reorder_usernames(
        self,
        channel: PeerRef,
        usernames: list[str],
        *,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            ChannelsReorderUsernames(
                channel=await resolve_input_channel(self._raw, channel, timeout=timeout),
                order=[str(item) for item in usernames],
            ),
            timeout=timeout,
        )

    async def update_slow_mode(
        self,
        channel: PeerRef,
        seconds: int,
        *,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            ChannelsToggleSlowMode(
                channel=await resolve_input_channel(self._raw, channel, timeout=timeout),
                seconds=int(seconds),
            ),
            timeout=timeout,
        )


class ChannelAdminLogAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def list(
        self,
        channel: PeerRef,
        *,
        q: str | None = None,
        events_filter: Any | None = None,
        admins: list[Any] | None = None,
        max_id: int = 0,
        min_id: int = 0,
        limit: int = 100,
        timeout: float = 20.0,
    ) -> Any:
        flags = 0
        if q is not None:
            flags |= 1
        if events_filter is not None:
            flags |= 2
        if admins is not None:
            flags |= 4
        return await self._raw.invoke_api(
            ChannelsGetAdminLog(
                flags=flags,
                channel=await resolve_input_channel(self._raw, channel, timeout=timeout),
                q=str(q) if q is not None else None,
                events_filter=events_filter,
                admins=list(admins) if admins is not None else None,
                max_id=int(max_id),
                min_id=int(min_id),
                limit=int(limit),
            ),
            timeout=timeout,
        )


class ChannelLinksAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def message(
        self,
        channel: PeerRef,
        msg_id: int,
        *,
        grouped: bool = False,
        thread: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        flags = 0
        if grouped:
            flags |= 1
        if thread:
            flags |= 2
        return await self._raw.invoke_api(
            ChannelsExportMessageLink(
                flags=flags,
                grouped=True if grouped else None,
                thread=True if thread else None,
                channel=await resolve_input_channel(self._raw, channel, timeout=timeout),
                id=int(msg_id),
            ),
            timeout=timeout,
        )


class ChannelsAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw
        self.settings = ChannelSettingsAPI(raw)
        self.admin_log = ChannelAdminLogAPI(raw)
        self.links = ChannelLinksAPI(raw)

    async def read_history(
        self,
        channel: PeerRef,
        *,
        max_id: int = 0,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            ChannelsReadHistory(
                channel=await resolve_input_channel(self._raw, channel, timeout=timeout),
                max_id=int(max_id),
            ),
            timeout=timeout,
        )

    async def delete_history(
        self,
        channel: PeerRef,
        *,
        for_everyone: bool = False,
        max_id: int = 0,
        timeout: float = 20.0,
    ) -> Any:
        flags = 1 if for_everyone else 0
        return await self._raw.invoke_api(
            ChannelsDeleteHistory(
                flags=flags,
                for_everyone=True if for_everyone else None,
                channel=await resolve_input_channel(self._raw, channel, timeout=timeout),
                max_id=int(max_id),
            ),
            timeout=timeout,
        )

    async def delete_participant_history(
        self,
        channel: PeerRef,
        participant: PeerRef,
        *,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            ChannelsDeleteParticipantHistory(
                channel=await resolve_input_channel(self._raw, channel, timeout=timeout),
                participant=await resolve_input_peer(self._raw, participant, timeout=timeout),
            ),
            timeout=timeout,
        )
