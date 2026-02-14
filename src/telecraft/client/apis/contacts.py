from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from telecraft.client.apis._utils import resolve_input_user
from telecraft.client.peers import PeerRef
from telecraft.tl.generated.functions import UsersGetRequirementsToContact

if TYPE_CHECKING:
    from telecraft.client.mtproto import MtprotoClient


class ContactsRequirementsAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def to_contact(self, users: Sequence[PeerRef], *, timeout: float = 20.0) -> Any:
        payload = [await resolve_input_user(self._raw, user, timeout=timeout) for user in users]
        return await self._raw.invoke_api(
            UsersGetRequirementsToContact(id=payload),
            timeout=timeout,
        )


class ContactsAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw
        self.requirements = ContactsRequirementsAPI(raw)

    async def list(self, *, timeout: float = 20.0) -> list[Any]:
        return await self._raw.get_contacts(timeout=timeout)

    async def block(self, user: PeerRef, *, timeout: float = 20.0) -> Any:
        return await self._raw.block_user(user, timeout=timeout)

    async def unblock(self, user: PeerRef, *, timeout: float = 20.0) -> Any:
        return await self._raw.unblock_user(user, timeout=timeout)

    async def blocked(
        self,
        *,
        offset: int = 0,
        limit: int = 100,
        timeout: float = 20.0,
    ) -> Sequence[Any]:
        return await self._raw.get_blocked_users(offset=offset, limit=limit, timeout=timeout)

    async def send_card(
        self,
        peer: PeerRef,
        *,
        phone_number: str,
        first_name: str,
        last_name: str = "",
        vcard: str = "",
        reply_to_msg_id: int | None = None,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.send_contact(
            peer,
            phone_number=phone_number,
            first_name=first_name,
            last_name=last_name,
            vcard=vcard,
            reply_to_msg_id=reply_to_msg_id,
            timeout=timeout,
        )
