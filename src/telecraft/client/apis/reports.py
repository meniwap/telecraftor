from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from telecraft.client.apis._utils import resolve_input_peer
from telecraft.client.peers import PeerRef
from telecraft.client.reports import ReportReasonBuilder
from telecraft.tl.generated.functions import (
    AccountReportPeer,
    AccountReportProfilePhoto,
    MessagesReport,
    MessagesReportSpam,
    StoriesReport,
)

if TYPE_CHECKING:
    from telecraft.client.mtproto import MtprotoClient


def _to_reason_obj(reason: Any) -> Any:
    if not isinstance(reason, str):
        return reason
    normalized = reason.strip().lower().replace("-", "_").replace(" ", "_")
    mapping = {
        "spam": ReportReasonBuilder.spam,
        "violence": ReportReasonBuilder.violence,
        "pornography": ReportReasonBuilder.pornography,
        "child_abuse": ReportReasonBuilder.child_abuse,
        "copyright": ReportReasonBuilder.copyright,
        "illegal_drugs": ReportReasonBuilder.illegal_drugs,
        "personal_details": ReportReasonBuilder.personal_details,
        "fake": ReportReasonBuilder.fake,
        "geo_irrelevant": ReportReasonBuilder.geo_irrelevant,
    }
    factory = mapping.get(normalized)
    if factory is None:
        return ReportReasonBuilder.other(reason)
    return factory()


def _to_report_option(reason: Any) -> bytes:
    if isinstance(reason, bytes):
        return bytes(reason)
    if isinstance(reason, str):
        return reason.encode("utf-8")
    text = str(type(reason).__name__)
    return text.encode("utf-8")


class ReportsAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def peer(
        self,
        peer: PeerRef,
        reason: Any = b"r",
        *,
        message: str = "",
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            AccountReportPeer(
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                reason=_to_reason_obj(reason),
                message=str(message),
            ),
            timeout=timeout,
        )

    async def messages(
        self,
        peer: PeerRef,
        msg_ids: int | Sequence[int],
        reason: Any = b"r",
        *,
        message: str = "",
        timeout: float = 20.0,
    ) -> Any:
        ids = [int(msg_ids)] if isinstance(msg_ids, int) else [int(x) for x in msg_ids]
        return await self._raw.invoke_api(
            MessagesReport(
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                id=ids,
                option=_to_report_option(reason),
                message=str(message),
            ),
            timeout=timeout,
        )

    async def story(
        self,
        peer: PeerRef,
        story_id: int = 1,
        reason: Any = b"r",
        *,
        message: str = "",
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            StoriesReport(
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                id=[int(story_id)],
                option=_to_report_option(reason),
                message=str(message),
            ),
            timeout=timeout,
        )

    async def profile_photo(
        self,
        peer: PeerRef,
        photo_id: int,
        reason: Any = b"r",
        *,
        message: str = "",
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            AccountReportProfilePhoto(
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                photo_id=int(photo_id),
                reason=_to_reason_obj(reason),
                message=str(message),
            ),
            timeout=timeout,
        )

    async def spam(self, peer: PeerRef, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            MessagesReportSpam(peer=await resolve_input_peer(self._raw, peer, timeout=timeout)),
            timeout=timeout,
        )

    async def spam_peer(self, peer: PeerRef, *, message: str = "", timeout: float = 20.0) -> Any:
        return await self.peer(peer, "spam", message=message, timeout=timeout)

    async def fake_peer(self, peer: PeerRef, *, message: str = "", timeout: float = 20.0) -> Any:
        return await self.peer(peer, "fake", message=message, timeout=timeout)

    async def violence_peer(
        self,
        peer: PeerRef,
        *,
        message: str = "",
        timeout: float = 20.0,
    ) -> Any:
        return await self.peer(peer, "violence", message=message, timeout=timeout)

    async def copyright_peer(
        self,
        peer: PeerRef,
        *,
        message: str = "",
        timeout: float = 20.0,
    ) -> Any:
        return await self.peer(peer, "copyright", message=message, timeout=timeout)

    async def pornography_peer(
        self,
        peer: PeerRef,
        *,
        message: str = "",
        timeout: float = 20.0,
    ) -> Any:
        return await self.peer(peer, "pornography", message=message, timeout=timeout)

    async def messages_spam(
        self,
        peer: PeerRef,
        msg_ids: int | Sequence[int],
        *,
        message: str = "",
        timeout: float = 20.0,
    ) -> Any:
        return await self.messages(
            peer,
            msg_ids,
            "spam",
            message=message,
            timeout=timeout,
        )
