from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from telecraft.client.peers import PeerRef

if TYPE_CHECKING:
    from telecraft.client.mtproto import MtprotoClient


class MediaAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def send_file(
        self,
        peer: PeerRef,
        path: str | Path,
        *,
        caption: str | None = None,
        as_photo: bool | None = None,
        reply_to_msg_id: int | None = None,
        silent: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.send_file(
            peer,
            path,
            caption=caption,
            as_photo=as_photo,
            reply_to_msg_id=reply_to_msg_id,
            silent=silent,
            timeout=timeout,
        )

    async def send_album(
        self,
        peer: PeerRef,
        paths: list[str | Path],
        *,
        captions: list[str] | None = None,
        reply_to_msg_id: int | None = None,
        silent: bool = False,
        timeout: float = 60.0,
    ) -> Any:
        return await self._raw.send_album(
            peer,
            paths,
            captions=captions,
            reply_to_msg_id=reply_to_msg_id,
            silent=silent,
            timeout=timeout,
        )

    async def download(
        self,
        message_or_event: Any,
        *,
        dest: str | None = None,
        timeout: float = 60.0,
    ) -> Any:
        return await self._raw.download_media(message_or_event, dest=dest, timeout=timeout)

    async def send_location(
        self,
        peer: PeerRef,
        *,
        latitude: float,
        longitude: float,
        accuracy_radius: int | None = None,
        reply_to_msg_id: int | None = None,
        silent: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.send_location(
            peer,
            latitude=latitude,
            longitude=longitude,
            accuracy_radius=accuracy_radius,
            reply_to_msg_id=reply_to_msg_id,
            silent=silent,
            timeout=timeout,
        )

    async def send_live_location(
        self,
        peer: PeerRef,
        *,
        latitude: float,
        longitude: float,
        period: int,
        heading: int | None = None,
        proximity_notification_radius: int | None = None,
        accuracy_radius: int | None = None,
        reply_to_msg_id: int | None = None,
        silent: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.send_live_location(
            peer,
            latitude=latitude,
            longitude=longitude,
            period=period,
            heading=heading,
            proximity_notification_radius=proximity_notification_radius,
            accuracy_radius=accuracy_radius,
            reply_to_msg_id=reply_to_msg_id,
            silent=silent,
            timeout=timeout,
        )

    async def stop_live_location(
        self,
        peer: PeerRef,
        *,
        msg_id: int,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.stop_live_location(peer, msg_id=msg_id, timeout=timeout)

    async def sticker_set(self, name: str, *, timeout: float = 20.0) -> Any:
        return await self._raw.get_sticker_set(name, timeout=timeout)

    async def send_sticker(
        self,
        peer: PeerRef,
        sticker_id: int,
        sticker_access_hash: int,
        sticker_file_reference: bytes,
        *,
        reply_to_msg_id: int | None = None,
        silent: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.send_sticker(
            peer,
            sticker_id,
            sticker_access_hash,
            sticker_file_reference,
            reply_to_msg_id=reply_to_msg_id,
            silent=silent,
            timeout=timeout,
        )

    async def send_voice(
        self,
        peer: PeerRef,
        path: str,
        *,
        caption: str | None = None,
        duration: int | None = None,
        waveform: bytes | None = None,
        reply_to_msg_id: int | None = None,
        silent: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.send_voice(
            peer,
            path,
            caption=caption,
            duration=duration,
            waveform=waveform,
            reply_to_msg_id=reply_to_msg_id,
            silent=silent,
            timeout=timeout,
        )

    async def send_video_note(
        self,
        peer: PeerRef,
        path: str | Path,
        *,
        duration: int | None = None,
        length: int = 240,
        reply_to_msg_id: int | None = None,
        silent: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.send_video_note(
            peer,
            path,
            duration=duration,
            length=length,
            reply_to_msg_id=reply_to_msg_id,
            silent=silent,
            timeout=timeout,
        )
