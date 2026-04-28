from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from apps.streamingbot.bot_api import BotApiClient, BotApiConfig, BotApiError


def _make_client() -> BotApiClient:
    return BotApiClient(BotApiConfig(token="123:abc"))


def test_streamingbot_bot_api__get_updates__sends_expected_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    def fake_request_sync(method: str, payload: dict[str, Any]) -> Any:
        seen["method"] = method
        seen["payload"] = payload
        return [{"update_id": 1, "message": {"message_id": 2}}]

    client = _make_client()
    monkeypatch.setattr(client, "_request_sync", fake_request_sync)

    out = asyncio.run(client.get_updates(offset=99, timeout=30))
    assert out == [{"update_id": 1, "message": {"message_id": 2}}]
    assert seen["method"] == "getUpdates"
    assert seen["payload"] == {
        "offset": 99,
        "timeout": 30,
        "allowed_updates": ["message", "callback_query"],
    }


def test_streamingbot_bot_api__send_message__includes_reply_markup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    def fake_request_sync(method: str, payload: dict[str, Any]) -> Any:
        seen["method"] = method
        seen["payload"] = payload
        return {"message_id": 99}

    client = _make_client()
    monkeypatch.setattr(client, "_request_sync", fake_request_sync)

    out = asyncio.run(
        client.send_message(
            chat_id=7,
            text="שלום",
            reply_markup={"inline_keyboard": [[{"text": "x", "callback_data": "menu"}]]},
        )
    )
    assert out == {"message_id": 99}
    assert seen["method"] == "sendMessage"
    assert seen["payload"] == {
        "chat_id": 7,
        "text": "שלום",
        "reply_markup": {"inline_keyboard": [[{"text": "x", "callback_data": "menu"}]]},
    }


def test_streamingbot_bot_api__send_message_draft__sends_expected_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    def fake_request_sync(method: str, payload: dict[str, Any]) -> Any:
        seen["method"] = method
        seen["payload"] = payload
        return True

    client = _make_client()
    monkeypatch.setattr(client, "_request_sync", fake_request_sync)

    out = asyncio.run(client.send_message_draft(chat_id=7, draft_id=42, text="שלום"))
    assert out is True
    assert seen["method"] == "sendMessageDraft"
    assert seen["payload"] == {"chat_id": 7, "draft_id": 42, "text": "שלום"}


def test_streamingbot_bot_api__send_chat_action__sends_typing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    def fake_request_sync(method: str, payload: dict[str, Any]) -> Any:
        seen["method"] = method
        seen["payload"] = payload
        return True

    client = _make_client()
    monkeypatch.setattr(client, "_request_sync", fake_request_sync)

    out = asyncio.run(client.send_chat_action(chat_id=7))
    assert out is True
    assert seen["method"] == "sendChatAction"
    assert seen["payload"] == {"chat_id": 7, "action": "typing"}


def test_streamingbot_bot_api__answer_callback_query__sends_expected_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    def fake_request_sync(method: str, payload: dict[str, Any]) -> Any:
        seen["method"] = method
        seen["payload"] = payload
        return True

    client = _make_client()
    monkeypatch.setattr(client, "_request_sync", fake_request_sync)

    out = asyncio.run(client.answer_callback_query(callback_query_id="cbq-1", text="ok"))
    assert out is True
    assert seen["method"] == "answerCallbackQuery"
    assert seen["payload"] == {"callback_query_id": "cbq-1", "text": "ok"}


def test_streamingbot_bot_api__request_sync__raises_on_ok_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Resp:
        def __enter__(self) -> _Resp:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            payload = {"ok": False, "error_code": 400, "description": "bad request"}
            return json.dumps(payload).encode("utf-8")

    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: _Resp())
    client = _make_client()
    with pytest.raises(BotApiError):
        client._request_sync("sendMessage", {"chat_id": 1, "text": "x"})


def test_streamingbot_bot_api__request_sync__raises_on_network_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*_args: object, **_kwargs: object) -> Any:
        raise OSError("boom")

    monkeypatch.setattr("urllib.request.urlopen", fail)
    client = _make_client()
    with pytest.raises(BotApiError):
        client._request_sync("sendMessage", {"chat_id": 1, "text": "x"})
