from __future__ import annotations

from typing import TYPE_CHECKING, Any

from telecraft.tl.generated.functions import (
    HelpGetAppConfig,
    HelpGetAppUpdate,
    HelpGetConfig,
    HelpGetCountriesList,
    HelpGetNearestDc,
    HelpGetSupport,
    HelpGetSupportName,
    HelpGetTimezonesList,
)

if TYPE_CHECKING:
    from telecraft.client.mtproto import MtprotoClient


class HelpAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def config(self, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(HelpGetConfig(), timeout=timeout)

    async def nearest_dc(self, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(HelpGetNearestDc(), timeout=timeout)

    async def app_config(self, *, hash: int = 0, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(HelpGetAppConfig(hash=int(hash)), timeout=timeout)

    async def app_update(self, *, source: str = "", timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(HelpGetAppUpdate(source=str(source)), timeout=timeout)

    async def countries_list(
        self,
        *,
        lang_code: str = "en",
        hash: int = 0,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            HelpGetCountriesList(lang_code=str(lang_code), hash=int(hash)),
            timeout=timeout,
        )

    async def support_name(self, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(HelpGetSupportName(), timeout=timeout)

    async def support(self, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(HelpGetSupport(), timeout=timeout)

    async def timezones_list(self, *, hash: int = 0, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(HelpGetTimezonesList(hash=int(hash)), timeout=timeout)
