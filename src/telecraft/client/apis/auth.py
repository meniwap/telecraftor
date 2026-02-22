from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from telecraft.client.auth import build_import_authorization, build_login_token
from telecraft.tl.generated.functions import (
    AuthAcceptLoginToken,
    AuthExportAuthorization,
    AuthExportLoginToken,
    AuthImportAuthorization,
    AuthImportBotAuthorization,
    AuthImportLoginToken,
    AuthLogOut,
    AuthRecoverPassword,
    AuthRequestPasswordRecovery,
    AuthResetAuthorizations,
)

if TYPE_CHECKING:
    from telecraft.client.mtproto import MtprotoClient


class AuthAPI:
    def __init__(self, raw: MtprotoClient) -> None:
        self._raw = raw

    def _api_credentials(
        self,
        *,
        api_id: int | None,
        api_hash: str | None,
    ) -> tuple[int, str]:
        init = getattr(self._raw, "_init", None)
        resolved_api_id = api_id if api_id is not None else getattr(init, "api_id", 0)
        resolved_api_hash = api_hash if api_hash is not None else getattr(init, "api_hash", "")
        return int(resolved_api_id or 0), str(resolved_api_hash or "")

    async def send_code(self, phone_number: str, *, timeout: float = 20.0) -> Any:
        return await self._raw.send_code(phone_number, timeout=timeout)

    async def sign_in(
        self,
        phone_number: str,
        phone_code_hash: str,
        phone_code: str,
        *,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.sign_in(
            phone_number=phone_number,
            phone_code_hash=phone_code_hash,
            phone_code=phone_code,
            timeout=timeout,
        )

    async def sign_up(
        self,
        phone_number: str,
        phone_code_hash: str,
        first_name: str,
        last_name: str = "",
        *,
        timeout: float = 20.0,
    ) -> Any:
        return await self._raw.sign_up(
            phone_number=phone_number,
            phone_code_hash=phone_code_hash,
            first_name=first_name,
            last_name=last_name,
            timeout=timeout,
        )

    async def check_password(self, password: str, *, timeout: float = 20.0) -> Any:
        return await self._raw.check_password(password, timeout=timeout)

    async def log_out(self, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(AuthLogOut(), timeout=timeout)

    async def reset_authorizations(self, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(AuthResetAuthorizations(), timeout=timeout)

    async def export_authorization(self, dc_id: int, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(AuthExportAuthorization(dc_id=int(dc_id)), timeout=timeout)

    async def import_authorization(
        self,
        id: int,  # noqa: A002
        bytes: Any,  # noqa: A002
        *,
        timeout: float = 20.0,
    ) -> Any:
        import_id, import_payload = build_import_authorization(id, bytes)
        return await self._raw.invoke_api(
            AuthImportAuthorization(id=int(import_id), bytes=import_payload),
            timeout=timeout,
        )

    async def export_login_token(
        self,
        *,
        except_ids: Sequence[int] | None = None,
        api_id: int | None = None,
        api_hash: str | None = None,
        timeout: float = 20.0,
    ) -> Any:
        resolved_api_id, resolved_api_hash = self._api_credentials(api_id=api_id, api_hash=api_hash)
        return await self._raw.invoke_api(
            AuthExportLoginToken(
                api_id=resolved_api_id,
                api_hash=resolved_api_hash,
                except_ids=[int(x) for x in (except_ids or [])],
            ),
            timeout=timeout,
        )

    async def import_login_token(self, token: Any, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            AuthImportLoginToken(token=build_login_token(token)),
            timeout=timeout,
        )

    async def accept_login_token(self, token: Any, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(
            AuthAcceptLoginToken(token=build_login_token(token)),
            timeout=timeout,
        )

    async def import_bot_authorization(
        self,
        bot_auth_token: Any,
        *,
        api_id: int | None = None,
        api_hash: str | None = None,
        flags: int = 0,
        timeout: float = 20.0,
    ) -> Any:
        resolved_api_id, resolved_api_hash = self._api_credentials(api_id=api_id, api_hash=api_hash)
        return await self._raw.invoke_api(
            AuthImportBotAuthorization(
                flags=int(flags),
                api_id=resolved_api_id,
                api_hash=resolved_api_hash,
                bot_auth_token=bot_auth_token,
            ),
            timeout=timeout,
        )

    async def request_password_recovery(self, *, timeout: float = 20.0) -> Any:
        return await self._raw.invoke_api(AuthRequestPasswordRecovery(), timeout=timeout)

    async def recover_password(
        self,
        code: Any,
        *,
        new_settings: Any | None = None,
        timeout: float = 20.0,
    ) -> Any:
        flags = 1 if new_settings is not None else 0
        return await self._raw.invoke_api(
            AuthRecoverPassword(
                flags=flags,
                code=code,
                new_settings=new_settings,
            ),
            timeout=timeout,
        )
