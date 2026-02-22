from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from telecraft.client.apis._utils import resolve_input_user
from telecraft.client.peers import PeerRef
from telecraft.tl.generated.functions import UsersGetFullUser, UsersGetUsers
from telecraft.tl.generated.types import InputUserSelf

if TYPE_CHECKING:
    from telecraft.client.mtproto import MtprotoClient


def _is_self_ref(value: Any) -> bool:
    return isinstance(value, str) and value.strip().lower() in {"self", "me"}


class UsersAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def get(
        self,
        users: PeerRef | Sequence[PeerRef],
        *,
        timeout: float = 20.0,
    ) -> Any:
        if isinstance(users, (str, tuple)):
            refs: list[Any] = [users]
        else:
            refs = list(users)
        payload: list[Any] = []
        for user in refs:
            if _is_self_ref(user):
                payload.append(InputUserSelf())
            else:
                payload.append(await resolve_input_user(self._raw, user, timeout=timeout))
        return await self._raw.invoke_api(UsersGetUsers(id=payload), timeout=timeout)

    async def full(self, user: PeerRef | str = "self", *, timeout: float = 20.0) -> Any:
        input_user: Any
        if _is_self_ref(user):
            input_user = InputUserSelf()
        else:
            input_user = await resolve_input_user(self._raw, user, timeout=timeout)
        return await self._raw.invoke_api(UsersGetFullUser(id=input_user), timeout=timeout)
