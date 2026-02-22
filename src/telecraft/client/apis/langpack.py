from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from telecraft.tl.generated.functions import (
    LangpackGetDifference,
    LangpackGetLanguage,
    LangpackGetLanguages,
    LangpackGetLangPack,
    LangpackGetStrings,
)

if TYPE_CHECKING:
    from telecraft.client.mtproto import MtprotoClient


class LangpackAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def languages(self, *, lang_pack: str = "", timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            LangpackGetLanguages(lang_pack=lang_pack),
            timeout=timeout,
        )

    async def language(self, lang_code: str, *, lang_pack: str = "", timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            LangpackGetLanguage(lang_pack=lang_pack, lang_code=lang_code),
            timeout=timeout,
        )

    async def strings(
        self,
        lang_code: str,
        keys: Sequence[str] | str | Any | None = None,
        *,
        lang_pack: str = "",
        timeout: float = 20.0,
    ) -> Any:
        if keys is None:
            keys_payload = []
        elif isinstance(keys, (str, bytes, bytearray)):
            keys_payload = [keys]
        elif isinstance(keys, Sequence):
            keys_payload = list(keys)
        else:
            keys_payload = [keys]
        return await self._raw.invoke_api(
            LangpackGetStrings(
                lang_pack=lang_pack,
                lang_code=lang_code,
                keys=keys_payload,
            ),
            timeout=timeout,
        )

    async def difference(
        self,
        lang_code: str,
        from_version: int,
        *,
        lang_pack: str = "",
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            LangpackGetDifference(
                lang_pack=lang_pack,
                lang_code=lang_code,
                from_version=int(from_version),
            ),
            timeout=timeout,
        )

    async def pack(self, lang_code: str, *, lang_pack: str = "", timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            LangpackGetLangPack(lang_pack=lang_pack, lang_code=lang_code),
            timeout=timeout,
        )
