from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from telecraft.client.apis._utils import resolve_input_user
from telecraft.client.peers import PeerRef
from telecraft.tl.generated.functions import (
    BotsAllowSendMessage,
    BotsCanSendMessage,
    BotsGetBotCommands,
    BotsGetBotMenuButton,
    BotsResetBotCommands,
    BotsSetBotCommands,
    BotsSetBotMenuButton,
)
from telecraft.tl.generated.types import BotCommandScopeDefault, BotMenuButtonDefault, InputUserEmpty

if TYPE_CHECKING:
    from telecraft.client.mtproto import MtprotoClient


def _scope_or_default(scope: Any | None) -> Any:
    return scope if scope is not None else BotCommandScopeDefault()


class BotsAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def set_commands(
        self,
        commands: Sequence[Any] | None = None,
        *,
        scope: Any | None = None,
        lang_code: str = "",
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            BotsSetBotCommands(
                scope=_scope_or_default(scope),
                lang_code=str(lang_code),
                commands=list(commands) if commands is not None else [],
            ),
            timeout=timeout,
        )

    async def reset_commands(
        self,
        *,
        scope: Any | None = None,
        lang_code: str = "",
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            BotsResetBotCommands(
                scope=_scope_or_default(scope),
                lang_code=str(lang_code),
            ),
            timeout=timeout,
        )

    async def get_commands(
        self,
        *,
        scope: Any | None = None,
        lang_code: str = "",
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            BotsGetBotCommands(
                scope=_scope_or_default(scope),
                lang_code=str(lang_code),
            ),
            timeout=timeout,
        )

    async def set_menu_button(
        self,
        button: Any | None = None,
        *,
        user: PeerRef | None = None,
        timeout: float = 20.0,
    ) -> Any:
        input_user = (
            await resolve_input_user(self._raw, user, timeout=timeout)
            if user is not None
            else InputUserEmpty()
        )
        return await self._raw.invoke_api(
            BotsSetBotMenuButton(
                user_id=input_user,
                button=button if button is not None else BotMenuButtonDefault(),
            ),
            timeout=timeout,
        )

    async def get_menu_button(
        self,
        *,
        user: PeerRef | None = None,
        timeout: float = 20.0,
    ) -> Any:
        input_user = (
            await resolve_input_user(self._raw, user, timeout=timeout)
            if user is not None
            else InputUserEmpty()
        )
        return await self._raw.invoke_api(
            BotsGetBotMenuButton(user_id=input_user),
            timeout=timeout,
        )

    async def can_send_message(self, bot: PeerRef = "user:1", *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            BotsCanSendMessage(bot=await resolve_input_user(self._raw, bot, timeout=timeout)),
            timeout=timeout,
        )

    async def allow_send_message(self, bot: PeerRef = "user:1", *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            BotsAllowSendMessage(bot=await resolve_input_user(self._raw, bot, timeout=timeout)),
            timeout=timeout,
        )
