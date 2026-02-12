from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from telecraft.client.account import (
    AuthorizationRef,
    ThemeRef,
    WallpaperRef,
    WebAuthorizationRef,
    build_input_theme,
    build_input_wallpaper,
)
from telecraft.client.apis._utils import resolve_input_peer
from telecraft.client.peers import PeerRef
from telecraft.tl.generated.functions import (
    AccountGetAuthorizations,
    AccountGetContentSettings,
    AccountGetMultiWallPapers,
    AccountGetTheme,
    AccountGetThemes,
    AccountGetWallPaper,
    AccountGetWallPapers,
    AccountGetWebAuthorizations,
    AccountInstallTheme,
    AccountInstallWallPaper,
    AccountResetAuthorization,
    AccountResetWallPapers,
    AccountResetWebAuthorization,
    AccountResetWebAuthorizations,
    AccountSaveWallPaper,
    AccountSetContentSettings,
    AccountUploadWallPaper,
    AuthResetAuthorizations,
    HelpAcceptTermsOfService,
    HelpGetTermsOfServiceUpdate,
    MessagesGetDefaultHistoryTtl,
    MessagesSetChatWallPaper,
    MessagesSetDefaultHistoryTtl,
)

if TYPE_CHECKING:
    from telecraft.client.mtproto import MtprotoClient


def _authorization_hash(value: int | AuthorizationRef) -> int:
    if isinstance(value, AuthorizationRef):
        return int(value.hash)
    return int(value)


def _web_authorization_hash(value: int | WebAuthorizationRef) -> int:
    if isinstance(value, WebAuthorizationRef):
        return int(value.hash)
    return int(value)


def _extract_tos_id(id_or_obj: Any) -> Any:
    if hasattr(id_or_obj, "TL_NAME"):
        return id_or_obj
    if hasattr(id_or_obj, "id"):
        return getattr(id_or_obj, "id")
    return id_or_obj


class AccountSessionsAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def list(self, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(AccountGetAuthorizations(), timeout=timeout)

    async def terminate(self, hash: int | AuthorizationRef, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            AccountResetAuthorization(hash=_authorization_hash(hash)),
            timeout=timeout,
        )

    async def terminate_others(self, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(AuthResetAuthorizations(), timeout=timeout)

    async def count(self, *, timeout: float = 20.0) -> int:
        out = await self.list(timeout=timeout)
        authorizations = getattr(out, "authorizations", None)
        if isinstance(authorizations, list):
            return len(authorizations)
        return 0


class AccountWebSessionsAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def list(self, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(AccountGetWebAuthorizations(), timeout=timeout)

    async def terminate(self, hash: int | WebAuthorizationRef, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            AccountResetWebAuthorization(hash=_web_authorization_hash(hash)),
            timeout=timeout,
        )

    async def terminate_all(self, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(AccountResetWebAuthorizations(), timeout=timeout)

    async def count(self, *, timeout: float = 20.0) -> int:
        out = await self.list(timeout=timeout)
        authorizations = getattr(out, "authorizations", None)
        if isinstance(authorizations, list):
            return len(authorizations)
        return 0


class AccountContentAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def get(self, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(AccountGetContentSettings(), timeout=timeout)

    async def set(self, sensitive_enabled: bool, *, timeout: float = 20.0) -> Any:
        flags = 1 if sensitive_enabled else 0
        return await self._raw.invoke_api(
            AccountSetContentSettings(
                flags=flags,
                sensitive_enabled=True if sensitive_enabled else None,
            ),
            timeout=timeout,
        )

    async def sensitive_enabled(self, *, timeout: float = 20.0) -> bool:
        out = await self.get(timeout=timeout)
        value = getattr(out, "sensitive_enabled", None)
        return bool(value)


class AccountTTLAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def get_default(self, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(MessagesGetDefaultHistoryTtl(), timeout=timeout)

    async def set_default(self, days: int = 1, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            MessagesSetDefaultHistoryTtl(period=int(days)),
            timeout=timeout,
        )

    async def disable(self, *, timeout: float = 20.0) -> Any:
        return await self.set_default(0, timeout=timeout)


class AccountTermsAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def get_update(self, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(HelpGetTermsOfServiceUpdate(), timeout=timeout)

    async def accept(self, id_or_obj: Any = 0, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            HelpAcceptTermsOfService(id=_extract_tos_id(id_or_obj)),
            timeout=timeout,
        )

    async def needs_acceptance(self, *, timeout: float = 20.0) -> bool:
        out = await self.get_update(timeout=timeout)
        return getattr(out, "TL_NAME", "").endswith("termsOfServiceUpdate")


class AccountThemesAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def list(self, *, format: str = "android", hash: int = 0, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            AccountGetThemes(format=str(format), hash=int(hash)),
            timeout=timeout,
        )

    async def get(
        self,
        ref: ThemeRef | Any,
        *,
        format: str = "android",
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            AccountGetTheme(format=str(format), theme=build_input_theme(ref)),
            timeout=timeout,
        )

    async def install(
        self,
        ref: ThemeRef | Any,
        *,
        dark: bool = False,
        format: str = "android",
        base_theme: Any | None = None,
        timeout: float = 20.0,
    ) -> Any:
        flags = 0
        if dark:
            flags |= 1
        if base_theme is not None:
            flags |= 2
        return await self._raw.invoke_api(
            AccountInstallTheme(
                flags=flags,
                dark=True if dark else None,
                theme=build_input_theme(ref),
                format=str(format),
                base_theme=base_theme,
            ),
            timeout=timeout,
        )

    async def list_android(self, *, hash: int = 0, timeout: float = 20.0) -> Any:
        return await self.list(format="android", hash=hash, timeout=timeout)

    async def list_ios(self, *, hash: int = 0, timeout: float = 20.0) -> Any:
        return await self.list(format="ios", hash=hash, timeout=timeout)

    async def list_tdesktop(self, *, hash: int = 0, timeout: float = 20.0) -> Any:
        return await self.list(format="tdesktop", hash=hash, timeout=timeout)


class AccountWallpapersAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    async def list(self, *, hash: int = 0, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(AccountGetWallPapers(hash=int(hash)), timeout=timeout)

    async def get(self, ref: WallpaperRef | Any, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            AccountGetWallPaper(wallpaper=build_input_wallpaper(ref)),
            timeout=timeout,
        )

    async def get_many(
        self,
        refs: Sequence[WallpaperRef | Any] = (),
        *,
        timeout: float = 20.0,
    ) -> Any:
        wallpapers = [build_input_wallpaper(ref) for ref in refs]
        return await self._raw.invoke_api(
            AccountGetMultiWallPapers(wallpapers=wallpapers),
            timeout=timeout,
        )

    async def search(
        self,
        q: str = "default",
        *,
        color: int | None = None,
        intensity: int | None = None,
        timeout: float = 20.0,
    ) -> Any:
        _ = (color, intensity)
        return await self._raw.invoke_api(
            AccountGetWallPaper(wallpaper=build_input_wallpaper(WallpaperRef.slug(str(q)))),
            timeout=timeout,
        )

    async def get_by_slug(self, slug: str = "default", *, timeout: float = 20.0) -> Any:
        return await self.get(WallpaperRef.slug(slug), timeout=timeout)

    async def save(
        self,
        ref: WallpaperRef | Any,
        *,
        unsave: bool = False,
        settings: Any | None = None,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            AccountSaveWallPaper(
                wallpaper=build_input_wallpaper(ref),
                unsave=bool(unsave),
                settings=settings,
            ),
            timeout=timeout,
        )

    async def set_for_peer(
        self,
        peer: PeerRef,
        wallpaper: WallpaperRef | Any | None,
        *,
        settings: Any | None = None,
        for_both: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        flags = 0
        if for_both:
            flags |= 1
        if wallpaper is None:
            flags |= 2
        return await self._raw.invoke_api(
            MessagesSetChatWallPaper(
                flags=flags,
                for_both=True if for_both else None,
                revert=True if wallpaper is None else None,
                peer=await resolve_input_peer(self._raw, peer, timeout=timeout),
                wallpaper=(
                    build_input_wallpaper(wallpaper)
                    if wallpaper is not None
                    else build_input_wallpaper(WallpaperRef.no_file(0))
                ),
                settings=settings,
                id=0,
            ),
            timeout=timeout,
        )

    async def reset(self, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(AccountResetWallPapers(), timeout=timeout)

    async def install(
        self,
        ref: WallpaperRef | Any,
        *,
        settings: Any | None = None,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.invoke_api(
            AccountInstallWallPaper(
                wallpaper=build_input_wallpaper(ref),
                settings=settings,
            ),
            timeout=timeout,
        )

    async def upload(
        self,
        file: Any,
        *,
        mime_type: str = "image/jpeg",
        settings: Any | None = None,
        for_chat: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        flags = 1 if for_chat else 0
        return await self._raw.invoke_api(
            AccountUploadWallPaper(
                flags=flags,
                for_chat=True if for_chat else None,
                file=file,
                mime_type=str(mime_type),
                settings=settings,
            ),
            timeout=timeout,
        )


class AccountAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw
        self.sessions = AccountSessionsAPI(raw)
        self.web_sessions = AccountWebSessionsAPI(raw)
        self.content = AccountContentAPI(raw)
        self.ttl = AccountTTLAPI(raw)
        self.terms = AccountTermsAPI(raw)
        self.themes = AccountThemesAPI(raw)
        self.wallpapers = AccountWallpapersAPI(raw)
