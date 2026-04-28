from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from apps.streamingbot.main import (
    LAST_REQUEST_MISSING_TEXT,
    MENU_TEXT,
    NO_ACTIVE_STREAM_TEXT,
    NON_PRIVATE_FALLBACK,
    RTL_MARK,
    STOPPED_STREAM_TEXT,
    WELCOME_TEXT,
    StreamingBotApp,
)
from apps.streamingbot.state import OffsetStore


class FakeBotApiClient:
    def __init__(self) -> None:
        self.sent_messages: list[dict[str, Any]] = []
        self.sent_drafts: list[dict[str, Any]] = []
        self.chat_actions: list[dict[str, Any]] = []
        self.answered_callbacks: list[dict[str, Any]] = []
        self.draft_started = asyncio.Event()
        self.draft_gate: asyncio.Event | None = None

    async def get_updates(self, *, offset: int | None, timeout: int = 30) -> list[dict[str, Any]]:
        raise AssertionError("get_updates should not be used in unit tests")

    async def send_message(
        self,
        *,
        chat_id: int,
        text: str,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = {"chat_id": chat_id, "text": text, "reply_markup": reply_markup}
        self.sent_messages.append(payload)
        return {"message_id": len(self.sent_messages)}

    async def send_message_draft(self, *, chat_id: int, draft_id: int, text: str) -> bool:
        payload = {"chat_id": chat_id, "draft_id": draft_id, "text": text}
        self.sent_drafts.append(payload)
        self.draft_started.set()
        if self.draft_gate is not None:
            await self.draft_gate.wait()
        return True

    async def send_chat_action(self, *, chat_id: int, action: str = "typing") -> bool:
        self.chat_actions.append({"chat_id": chat_id, "action": action})
        return True

    async def answer_callback_query(
        self,
        *,
        callback_query_id: str,
        text: str | None = None,
    ) -> bool:
        self.answered_callbacks.append(
            {"callback_query_id": callback_query_id, "text": text}
        )
        return True


def _make_app(tmp_path: Path, client: FakeBotApiClient) -> StreamingBotApp:
    return StreamingBotApp(
        client,
        offset_store=OffsetStore(tmp_path / "offset.json"),
        draft_step_delay=0,
        initial_typing_delay=0,
    )


def _message_update(
    update_id: int,
    *,
    chat_id: int = 1,
    text: str | None = "hello",
    chat_type: str = "private",
) -> dict[str, Any]:
    message: dict[str, Any] = {"chat": {"id": chat_id, "type": chat_type}}
    if text is not None:
        message["text"] = text
    return {"update_id": update_id, "message": message}


def _callback_update(
    update_id: int,
    *,
    chat_id: int = 1,
    data: str = "menu",
    chat_type: str = "private",
) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "callback_query": {
            "id": f"cbq-{update_id}",
            "data": data,
            "message": {"chat": {"id": chat_id, "type": chat_type}},
        },
    }


def test_streamingbot_main__non_private_message_gets_fallback(tmp_path: Path) -> None:
    async def scenario() -> None:
        client = FakeBotApiClient()
        app = _make_app(tmp_path, client)
        await app._dispatch_update(_message_update(1, chat_type="group", text="שלום"))
        assert client.sent_messages[0]["text"] == NON_PRIVATE_FALLBACK

    asyncio.run(scenario())


def test_streamingbot_main__start_sends_welcome_and_reply_keyboard(tmp_path: Path) -> None:
    async def scenario() -> None:
        client = FakeBotApiClient()
        app = _make_app(tmp_path, client)
        await app._dispatch_update(_message_update(1, text="/start"))
        assert client.sent_messages[0]["text"] == WELCOME_TEXT
        assert client.sent_messages[0]["reply_markup"] is not None
        assert "keyboard" in client.sent_messages[0]["reply_markup"]

    asyncio.run(scenario())


def test_streamingbot_main__menu_sends_inline_menu(tmp_path: Path) -> None:
    async def scenario() -> None:
        client = FakeBotApiClient()
        app = _make_app(tmp_path, client)
        await app._dispatch_update(_message_update(1, text="/menu"))
        assert client.sent_messages[0]["text"] == MENU_TEXT
        assert "inline_keyboard" in (client.sent_messages[0]["reply_markup"] or {})
        assert "keyboard" in (client.sent_messages[1]["reply_markup"] or {})

    asyncio.run(scenario())


def test_streamingbot_main__callback_query_triggers_answer_callback_query(tmp_path: Path) -> None:
    async def scenario() -> None:
        client = FakeBotApiClient()
        app = _make_app(tmp_path, client)
        await app._dispatch_update(_callback_update(1, data="menu"))
        assert client.answered_callbacks == [{"callback_query_id": "cbq-1", "text": None}]

    asyncio.run(scenario())


def test_streamingbot_main__rerun_last_without_history_sends_explanatory_message(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        client = FakeBotApiClient()
        app = _make_app(tmp_path, client)
        await app._dispatch_update(_callback_update(1, data="rerun:last"))
        assert client.sent_messages[0]["text"] == LAST_REQUEST_MISSING_TEXT

    asyncio.run(scenario())


def test_streamingbot_main__stop_without_active_task_returns_message(tmp_path: Path) -> None:
    async def scenario() -> None:
        client = FakeBotApiClient()
        app = _make_app(tmp_path, client)
        await app._dispatch_update(_message_update(1, text="/stop"))
        assert client.sent_messages[0]["text"] == NO_ACTIVE_STREAM_TEXT

    asyncio.run(scenario())


def test_streamingbot_main__cancellation_prevents_final_send(tmp_path: Path) -> None:
    async def scenario() -> None:
        client = FakeBotApiClient()
        client.draft_gate = asyncio.Event()
        app = _make_app(tmp_path, client)

        stream_task = asyncio.create_task(
            app._dispatch_update(_message_update(1, text="/joke קפה"))
        )
        await asyncio.wait_for(client.draft_started.wait(), timeout=1.0)
        await app._dispatch_update(_message_update(2, text="/stop"))
        client.draft_gate.set()
        await asyncio.wait_for(stream_task, timeout=1.0)

        texts = [message["text"] for message in client.sent_messages]
        assert STOPPED_STREAM_TEXT in texts
        assert not any(text.startswith("מצב: בדיחות") for text in texts)

    asyncio.run(scenario())


def test_streamingbot_main__final_generated_message_includes_inline_actions(tmp_path: Path) -> None:
    async def scenario() -> None:
        client = FakeBotApiClient()
        app = _make_app(tmp_path, client)
        await app._dispatch_update(_message_update(1, text="/fortune יום ראשון"))
        final_message = client.sent_messages[-1]
        assert final_message["text"].startswith(f"{RTL_MARK}מצב: תחזית")
        reply_markup = final_message["reply_markup"] or {}
        callback_data = [
            button["callback_data"]
            for row in reply_markup["inline_keyboard"]
            for button in row
        ]
        assert "rerun:last" in callback_data
        assert "menu" in callback_data

    asyncio.run(scenario())
