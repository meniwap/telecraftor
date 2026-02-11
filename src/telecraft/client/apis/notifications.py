from __future__ import annotations

from typing import TYPE_CHECKING, Any

from telecraft.client.apis._utils import resolve_input_peer
from telecraft.client.notifications import NotifyTarget
from telecraft.client.peers import PeerRef
from telecraft.tl.generated.functions import (
    AccountGetContactSignUpNotification,
    AccountGetNotifyExceptions,
    AccountGetNotifySettings,
    AccountGetReactionsNotifySettings,
    AccountResetNotifySettings,
    AccountSetContactSignUpNotification,
    AccountSetReactionsNotifySettings,
    AccountUpdateNotifySettings,
)
from telecraft.tl.generated.types import (
    InputNotifyBroadcasts,
    InputNotifyChats,
    InputNotifyForumTopic,
    InputNotifyPeer,
    InputNotifyUsers,
)

if TYPE_CHECKING:
    from telecraft.client.mtproto import MtprotoClient


async def _to_input_notify_target(raw: MtprotoClient, target: NotifyTarget, *, timeout: float) -> Any:
    if target.kind == "peer":
        if target.peer is None:
            raise ValueError("NotifyTarget.peer_target requires peer")
        input_peer = await resolve_input_peer(raw, target.peer, timeout=timeout)
        return InputNotifyPeer(peer=input_peer)
    if target.kind == "users":
        return InputNotifyUsers()
    if target.kind == "chats":
        return InputNotifyChats()
    if target.kind == "broadcasts":
        return InputNotifyBroadcasts()
    if target.kind == "forum_topic":
        if target.peer is None or target.top_msg_id is None:
            raise ValueError("NotifyTarget.forum_topic requires peer and top_msg_id")
        input_peer = await resolve_input_peer(raw, target.peer, timeout=timeout)
        return InputNotifyForumTopic(peer=input_peer, top_msg_id=int(target.top_msg_id))
    raise ValueError(f"Unsupported NotifyTarget kind: {target.kind!r}")


class NotificationsReactionsAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def get(self, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(AccountGetReactionsNotifySettings(), timeout=timeout)

    async def set(self, settings: Any, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            AccountSetReactionsNotifySettings(settings=settings),
            timeout=timeout,
        )


class NotificationsContactSignupAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def get(self, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(AccountGetContactSignUpNotification(), timeout=timeout)

    async def set(self, silent: bool, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            AccountSetContactSignUpNotification(silent=bool(silent)),
            timeout=timeout,
        )


class NotificationsAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw
        self.reactions = NotificationsReactionsAPI(raw)
        self.contact_signup = NotificationsContactSignupAPI(raw)

    async def get(self, target: NotifyTarget, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            AccountGetNotifySettings(peer=await _to_input_notify_target(self._raw, target, timeout=timeout)),
            timeout=timeout,
        )

    async def update(self, target: NotifyTarget, settings: Any, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            AccountUpdateNotifySettings(
                peer=await _to_input_notify_target(self._raw, target, timeout=timeout),
                settings=settings,
            ),
            timeout=timeout,
        )

    async def exceptions(
        self,
        *,
        peer_target: NotifyTarget | None = None,
        compare_sound: bool = False,
        compare_stories: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        flags = 0
        peer = None
        if peer_target is not None:
            flags |= 1
            peer = await _to_input_notify_target(self._raw, peer_target, timeout=timeout)
        if compare_sound:
            flags |= 2
        if compare_stories:
            flags |= 4
        return await self._raw.invoke_api(
            AccountGetNotifyExceptions(
                flags=flags,
                compare_sound=True if compare_sound else None,
                compare_stories=True if compare_stories else None,
                peer=peer,
            ),
            timeout=timeout,
        )

    async def reset(self, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(AccountResetNotifySettings(), timeout=timeout)

    @staticmethod
    def peer(peer: PeerRef) -> NotifyTarget:
        return NotifyTarget.peer_target(peer)
