from __future__ import annotations

import json
from secrets import randbits
from typing import TYPE_CHECKING, Any

from telecraft.client.apis._utils import resolve_input_peer
from telecraft.client.peers import PeerRef
from telecraft.tl.generated.functions import (
    BotsInvokeWebViewCustomMethod,
    MessagesProlongWebView,
    MessagesRequestAppWebView,
    MessagesRequestSimpleWebView,
    MessagesSendWebViewData,
)
from telecraft.tl.generated.types import DataJson, InputBotAppShortName, InputReplyToMessage

if TYPE_CHECKING:
    from telecraft.client.mtproto import MtprotoClient


def _as_json(value: Any) -> DataJson:
    if isinstance(value, DataJson):
        return value
    if isinstance(value, str):
        return DataJson(data=value)
    if isinstance(value, dict):
        return DataJson(data=json.dumps(value, ensure_ascii=False, separators=(",", ":")))
    return DataJson(data=str(value))


class WebAppsAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def request(
        self,
        peer: PeerRef | None = None,
        bot: PeerRef = "user:1",
        *,
        platform: str = "android",
        url: str | None = None,
        start_param: str | None = None,
        theme_params: Any | None = None,
        timeout: float = 20.0,
    ) -> Any:
        _ = peer
        flags = 0
        if url is not None:
            flags |= 1
        if start_param is not None:
            flags |= 2
        if theme_params is not None:
            flags |= 4
        return await self._raw.invoke_api(
            MessagesRequestSimpleWebView(
                flags=flags,
                from_switch_webview=None,
                from_side_menu=None,
                compact=None,
                fullscreen=None,
                bot=await resolve_input_peer(self._raw, bot, timeout=timeout),
                url=str(url) if url is not None else None,
                start_param=str(start_param) if start_param is not None else None,
                theme_params=_as_json(theme_params) if theme_params is not None else None,
                platform=str(platform),
            ),
            timeout=timeout,
        )

    async def request_app(
        self,
        peer: PeerRef,
        app: Any = "app",
        *,
        platform: str = "android",
        start_param: str | None = None,
        write_allowed: bool = False,
        theme_params: Any | None = None,
        timeout: float = 20.0,
    ) -> Any:
        app_obj = app
        if isinstance(app, str):
            app_obj = InputBotAppShortName(
                bot_id=await resolve_input_peer(self._raw, peer, timeout=timeout),
                short_name=str(app),
            )

        flags = 0
        if write_allowed:
            flags |= 1
        if start_param is not None:
            flags |= 2
        if theme_params is not None:
            flags |= 4

        return await self._raw.invoke_api(
            MessagesRequestAppWebView(
                flags=flags,
                write_allowed=True if write_allowed else None,
                compact=None,
                fullscreen=None,
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                app=app_obj,
                start_param=str(start_param) if start_param is not None else None,
                theme_params=_as_json(theme_params) if theme_params is not None else None,
                platform=str(platform),
            ),
            timeout=timeout,
        )

    async def prolong(
        self,
        peer: PeerRef,
        bot: PeerRef,
        query_id: int,
        *,
        reply_to_msg_id: int | None = None,
        send_as: PeerRef | None = None,
        silent: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        flags = 0
        if silent:
            flags |= 1
        if reply_to_msg_id is not None:
            flags |= 2
        if send_as is not None:
            flags |= 4
        return await self._raw.invoke_api(
            MessagesProlongWebView(
                flags=flags,
                silent=True if silent else None,
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                bot=await resolve_input_peer(self._raw, bot, timeout=timeout),
                query_id=int(query_id),
                reply_to=(
                    InputReplyToMessage(
                        flags=0,
                        reply_to_msg_id=int(reply_to_msg_id),
                        top_msg_id=None,
                        reply_to_peer_id=None,
                        quote_text=None,
                        quote_entities=None,
                        quote_offset=None,
                        monoforum_peer_id=None,
                        todo_item_id=None,
                    )
                    if reply_to_msg_id is not None
                    else None
                ),
                send_as=(
                    await resolve_input_peer(self._raw, send_as, timeout=timeout)
                    if send_as is not None
                    else None
                ),
            ),
            timeout=timeout,
        )

    async def send_data(
        self,
        bot: PeerRef,
        button_text: str,
        data: str | bytes,
        *,
        timeout: float = 20.0,
    ) -> Any:
        payload = data.encode("utf-8") if isinstance(data, str) else bytes(data)
        return await self._raw.invoke_api(
            MessagesSendWebViewData(
                bot=await resolve_input_peer(self._raw, bot, timeout=timeout),
                random_id=randbits(63),
                button_text=str(button_text),
                data=payload,
            ),
            timeout=timeout,
        )

    async def invoke_custom(
        self,
        bot: PeerRef,
        method: str,
        params: dict[str, Any] | str | DataJson,
        *,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            BotsInvokeWebViewCustomMethod(
                bot=await resolve_input_peer(self._raw, bot, timeout=timeout),
                custom_method=str(method),
                params=_as_json(params),
            ),
            timeout=timeout,
        )

    async def request_compact(
        self,
        *,
        bot: PeerRef,
        timeout: float = 20.0,
    ) -> Any:
        return await self.request(peer=None, bot=bot, platform="android", timeout=timeout)

    async def request_fullscreen(
        self,
        *,
        bot: PeerRef,
        timeout: float = 20.0,
    ) -> Any:
        return await self.request(peer=None, bot=bot, platform="ios", timeout=timeout)

    async def request_app_compact(
        self,
        peer: PeerRef,
        *,
        app: Any = "app",
        timeout: float = 20.0,
    ) -> Any:
        return await self.request_app(peer, app=app, platform="android", timeout=timeout)

    async def send_data_json(
        self,
        bot: PeerRef,
        button_text: str,
        payload: dict[str, Any],
        *,
        timeout: float = 20.0,
    ) -> Any:
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        return await self.send_data(bot, button_text, data, timeout=timeout)

    async def invoke_custom_json(
        self,
        bot: PeerRef,
        method: str,
        payload: dict[str, Any],
        *,
        timeout: float = 20.0,
    ) -> Any:
        return await self.invoke_custom(bot, method, payload, timeout=timeout)
