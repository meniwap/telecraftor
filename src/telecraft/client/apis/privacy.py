from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from telecraft.client.privacy import PrivacyKey, build_input_privacy_key
from telecraft.tl.generated.functions import (
    AccountGetGlobalPrivacySettings,
    AccountGetPrivacy,
    AccountSetGlobalPrivacySettings,
    AccountSetPrivacy,
)

if TYPE_CHECKING:
    from telecraft.client.mtproto import MtprotoClient


class PrivacyGlobalSettingsAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def get(self, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(AccountGetGlobalPrivacySettings(), timeout=timeout)

    async def set(self, settings: Any, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            AccountSetGlobalPrivacySettings(settings=settings),
            timeout=timeout,
        )


class PrivacyAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw
        self.global_settings = PrivacyGlobalSettingsAPI(raw)

    async def get(self, key: PrivacyKey | Any, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            AccountGetPrivacy(key=build_input_privacy_key(key)),
            timeout=timeout,
        )

    async def set(
        self, key: PrivacyKey | Any, rules: Sequence[Any], *, timeout: float = 20.0
    ) -> Any:
        return await self._raw.invoke_api(
            AccountSetPrivacy(
                key=build_input_privacy_key(key),
                rules=list(rules),
            ),
            timeout=timeout,
        )
