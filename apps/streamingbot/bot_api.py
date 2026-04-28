from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class BotApiConfig:
    token: str
    base_url: str = "https://api.telegram.org"


class BotApiError(RuntimeError):
    """Raised when Telegram Bot API returns an error or the request fails."""


class BotApiClient:
    def __init__(self, config: BotApiConfig) -> None:
        self._config = config

    def _build_url(self, method: str) -> str:
        token = self._config.token.strip()
        if not token:
            raise BotApiError("Missing bot token")
        return f"{self._config.base_url.rstrip('/')}/bot{token}/{method}"

    def _request_sync(self, method: str, payload: dict[str, Any]) -> Any:
        req = urllib.request.Request(
            url=self._build_url(method),
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=35) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            try:
                body = e.read().decode("utf-8", errors="replace")
            except Exception:
                body = ""
            raise BotApiError(
                f"HTTP {getattr(e, 'code', 'unknown')} calling {method}: {body[:300].strip()}"
            ) from e
        except (urllib.error.URLError, OSError) as e:
            raise BotApiError(f"Network error calling {method}: {e}") from e

        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError as e:
            raise BotApiError(f"Invalid JSON from {method}: {raw[:300]!r}") from e

        if not isinstance(decoded, dict):
            raise BotApiError(f"Unexpected response shape from {method}")
        if not decoded.get("ok", False):
            description = str(decoded.get("description", "unknown error"))
            error_code = decoded.get("error_code")
            if error_code is not None:
                raise BotApiError(f"{method} failed ({error_code}): {description}")
            raise BotApiError(f"{method} failed: {description}")
        return decoded.get("result")

    async def _request(self, method: str, payload: dict[str, Any]) -> Any:
        return await asyncio.to_thread(self._request_sync, method, payload)

    async def get_updates(self, *, offset: int | None, timeout: int = 30) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {
            "timeout": int(timeout),
            "allowed_updates": ["message", "callback_query"],
        }
        if offset is not None:
            payload["offset"] = int(offset)
        result = await self._request("getUpdates", payload)
        if not isinstance(result, list):
            raise BotApiError("getUpdates returned unexpected result shape")
        return [x for x in result if isinstance(x, dict)]

    async def send_message(
        self,
        *,
        chat_id: int,
        text: str,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "chat_id": int(chat_id),
            "text": str(text),
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        result = await self._request("sendMessage", payload)
        if not isinstance(result, dict):
            raise BotApiError("sendMessage returned unexpected result shape")
        return result

    async def send_message_draft(self, *, chat_id: int, draft_id: int, text: str) -> bool:
        result = await self._request(
            "sendMessageDraft",
            {
                "chat_id": int(chat_id),
                "draft_id": int(draft_id),
                "text": str(text),
            },
        )
        return bool(result)

    async def send_chat_action(self, *, chat_id: int, action: str = "typing") -> bool:
        result = await self._request(
            "sendChatAction",
            {
                "chat_id": int(chat_id),
                "action": str(action),
            },
        )
        return bool(result)

    async def answer_callback_query(
        self,
        *,
        callback_query_id: str,
        text: str | None = None,
    ) -> bool:
        payload: dict[str, Any] = {"callback_query_id": str(callback_query_id)}
        if text:
            payload["text"] = str(text)
        result = await self._request("answerCallbackQuery", payload)
        return bool(result)
