from __future__ import annotations

import argparse
import asyncio
import hashlib
import logging
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .bot_api import BotApiClient, BotApiConfig, BotApiError
from .commands import ParsedCommand, parse_text
from .content import ContentError, build_mode_lines, default_prompt_for_mode, final_title_for_mode
from .markup import make_inline_menu, make_reply_keyboard, make_result_actions
from .session import ChatSession, StreamRequest
from .state import OffsetState, OffsetStore

POLL_TIMEOUT_SECONDS = 30
DRAFT_STEP_DELAY_SECONDS = 0.45
INITIAL_TYPING_DELAY_SECONDS = 0.4
BACKOFF_SCHEDULE_SECONDS = (1.0, 2.0, 5.0)
OFFSET_PATH = Path(".sessions") / "streamingbot.offset.json"
RTL_MARK = "\u200f"
NON_PRIVATE_FALLBACK = "ה-streaming הרשמי הזה נתמך רק בשיחה פרטית עם הבוט. כתבו לי בפרטי."
EMPTY_TEXT_FALLBACK = "שלח לי טקסט או פקודה, ואני אענה ב-streaming."
NO_ACTIVE_STREAM_TEXT = "אין כרגע generation פעיל לעצור."
STOPPED_STREAM_TEXT = "עצרתי את ה-stream הנוכחי."
LAST_REQUEST_MISSING_TEXT = "אין עדיין בקשה קודמת. כתוב /menu או שלח שאלה."
UNKNOWN_CALLBACK_TEXT = "פקודה לא מוכרת."
GENERIC_ERROR_TEXT = "משהו השתבש בזמן generation. נסה שוב בעוד רגע."
WELCOME_TEXT = "\n".join(
    (
        "אני בוט streaming דמו: אני כותב draft בהדרגה ואז שולח תשובה סופית.",
        "",
        "נסה למשל:",
        "/joke קוד",
        "/story ישיבת צוות",
        "/battle חתול | כלב",
        "/fortune שבוע עבודה",
    )
)
HELP_TEXT = "\n".join(
    (
        "פקודות זמינות:",
        "/joke קוד",
        "/story ישיבת צוות",
        "/battle חתול | כלב",
        "/fortune שבוע עבודה",
        "/menu",
        "/stop",
    )
)
MENU_TEXT = "בחר מצב או כתוב פקודה:"
MENU_KEYBOARD_TEXT = "המקלדת המעודכנת מוכנה למטה."


def _try_load_env_file(path: str) -> None:
    p = Path(path)
    if not p.exists():
        return
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip("'").strip('"')
        if k and k not in os.environ:
            os.environ[k] = v


def _need(name: str) -> str:
    if name not in os.environ:
        _try_load_env_file("apps/env.sh")
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"Missing {name}. Run: source apps/env.sh")
    return value


def _draft_id_for_update(update_id: int, chat_id: int, prompt: str) -> int:
    material = f"{update_id}:{chat_id}:{prompt}".encode()
    digest = hashlib.sha256(material).digest()
    value = int.from_bytes(digest[:4], "big", signed=False)
    return max(1, value)


def _force_rtl_line(text: str) -> str:
    if not text:
        return text
    return f"{RTL_MARK}{text}"


class StreamingBotApp:
    def __init__(
        self,
        client: BotApiClient,
        *,
        offset_store: OffsetStore,
        draft_step_delay: float = DRAFT_STEP_DELAY_SECONDS,
        initial_typing_delay: float = INITIAL_TYPING_DELAY_SECONDS,
    ) -> None:
        self._client = client
        self._offset_store = offset_store
        self._draft_step_delay = draft_step_delay
        self._initial_typing_delay = initial_typing_delay
        self._log = logging.getLogger(__name__)
        self._sessions: dict[int, ChatSession] = {}
        self._background_tasks: set[asyncio.Task[Any]] = set()

    def _chat_session(self, chat_id: int) -> ChatSession:
        session = self._sessions.get(chat_id)
        if session is None:
            session = ChatSession(lock=asyncio.Lock())
            self._sessions[chat_id] = session
        return session

    def _track_task(self, task: asyncio.Task[Any]) -> None:
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def run_forever(self) -> None:
        state = self._offset_store.load()
        self._log.info("Polling started with offset=%s", state.next_update_id)
        backoff_index = 0
        while True:
            try:
                updates = await self._client.get_updates(
                    offset=state.next_update_id,
                    timeout=POLL_TIMEOUT_SECONDS,
                )
                backoff_index = 0
                for update in updates:
                    next_update_id = int(update.get("update_id", 0)) + 1
                    state = OffsetState(next_update_id=next_update_id)
                    self._offset_store.save(state)
                    task = asyncio.create_task(self._dispatch_update(update))
                    self._track_task(task)
            except BotApiError as ex:
                delay = BACKOFF_SCHEDULE_SECONDS[
                    min(backoff_index, len(BACKOFF_SCHEDULE_SECONDS) - 1)
                ]
                self._log.warning("Polling error: %s. Retrying in %.1fs", ex, delay)
                backoff_index += 1
                await asyncio.sleep(delay)

    async def _dispatch_update(self, update: dict[str, Any]) -> None:
        callback_query = update.get("callback_query")
        if isinstance(callback_query, dict):
            await self._handle_callback_query(update=update, callback_query=callback_query)
            return

        message = update.get("message")
        if isinstance(message, dict):
            await self._handle_message(update=update, message=message)

    async def _handle_message(self, *, update: dict[str, Any], message: dict[str, Any]) -> None:
        chat = message.get("chat")
        if not isinstance(chat, dict):
            return

        chat_id = int(chat["id"])
        chat_type = str(chat.get("type", "")).strip().lower()
        text = message.get("text")

        if chat_type != "private":
            if isinstance(text, str) and text.strip():
                await self._send_plain_reply(chat_id=chat_id, text=NON_PRIVATE_FALLBACK)
            return

        if not isinstance(text, str) or not text.strip():
            await self._send_private_reply(chat_id=chat_id, text=EMPTY_TEXT_FALLBACK)
            return

        update_id = int(update.get("update_id", 0))
        parsed = parse_text(text)
        await self._handle_private_command(
            chat_id=chat_id,
            update_id=update_id,
            parsed=parsed,
        )

    async def _handle_private_command(
        self,
        *,
        chat_id: int,
        update_id: int,
        parsed: ParsedCommand,
    ) -> None:
        if parsed.kind == "start":
            await self._send_private_reply(
                chat_id=chat_id,
                text=WELCOME_TEXT,
                reply_markup=make_reply_keyboard(),
                update_id=update_id,
            )
            return
        if parsed.kind == "help":
            await self._send_private_reply(
                chat_id=chat_id,
                text=HELP_TEXT,
                reply_markup=make_reply_keyboard(),
                update_id=update_id,
            )
            return
        if parsed.kind == "menu":
            await self._send_menu(chat_id=chat_id, update_id=update_id)
            return
        if parsed.kind == "stop":
            await self._stop_active_generation(chat_id=chat_id, update_id=update_id)
            return
        if parsed.kind == "error":
            await self._send_private_reply(
                chat_id=chat_id,
                text=parsed.text or UNKNOWN_CALLBACK_TEXT,
                reply_markup=make_reply_keyboard(),
                update_id=update_id,
            )
            return
        request = parsed.request
        if request is None:
            await self._send_private_reply(
                chat_id=chat_id,
                text=GENERIC_ERROR_TEXT,
                reply_markup=make_reply_keyboard(),
                update_id=update_id,
            )
            return
        await self._run_content_request(chat_id=chat_id, update_id=update_id, request=request)

    async def _handle_callback_query(
        self,
        *,
        update: dict[str, Any],
        callback_query: dict[str, Any],
    ) -> None:
        callback_id = callback_query.get("id")
        if isinstance(callback_id, str) and callback_id:
            try:
                await self._client.answer_callback_query(callback_query_id=callback_id)
            except BotApiError as ex:
                self._log.warning("answerCallbackQuery failed callback_id=%s: %s", callback_id, ex)

        message = callback_query.get("message")
        if not isinstance(message, dict):
            self._log.warning("Callback query missing message: %s", callback_query)
            return

        chat = message.get("chat")
        if not isinstance(chat, dict):
            return

        chat_id = chat.get("id")
        if not isinstance(chat_id, int):
            return

        chat_type = str(chat.get("type", "")).strip().lower()
        if chat_type != "private":
            await self._send_plain_reply(chat_id=chat_id, text=NON_PRIVATE_FALLBACK)
            return

        data = str(callback_query.get("data", "")).strip()
        update_id = int(update.get("update_id", 0))
        session = self._chat_session(chat_id)

        if data == "menu":
            await self._send_menu(chat_id=chat_id, update_id=update_id)
            return
        if data == "stop":
            await self._stop_active_generation(chat_id=chat_id, update_id=update_id)
            return
        if data == "rerun:last":
            request = session.last_request
            if request is None:
                await self._send_private_reply(
                    chat_id=chat_id,
                    text=LAST_REQUEST_MISSING_TEXT,
                    reply_markup=make_reply_keyboard(),
                    update_id=update_id,
                )
                return
            await self._run_content_request(chat_id=chat_id, update_id=update_id, request=request)
            return
        if data == "reroll:last":
            request = session.last_request
            if request is None:
                await self._send_private_reply(
                    chat_id=chat_id,
                    text=LAST_REQUEST_MISSING_TEXT,
                    reply_markup=make_reply_keyboard(),
                    update_id=update_id,
                )
                return
            rerolled = StreamRequest(
                mode=request.mode,
                prompt=request.prompt,
                variant=request.variant + 1,
            )
            await self._run_content_request(chat_id=chat_id, update_id=update_id, request=rerolled)
            return
        if data.startswith("mode:"):
            mode = data.split(":", 1)[1]
            if mode not in {"joke", "story", "fortune"}:
                await self._send_private_reply(
                    chat_id=chat_id,
                    text=UNKNOWN_CALLBACK_TEXT,
                    reply_markup=make_reply_keyboard(),
                    update_id=update_id,
                )
                return
            last_request = session.last_request
            prompt = (
                last_request.prompt
                if last_request is not None
                else default_prompt_for_mode(mode)
            )
            await self._run_content_request(
                chat_id=chat_id,
                update_id=update_id,
                request=StreamRequest(mode=mode, prompt=prompt),
            )
            return
        await self._send_private_reply(
            chat_id=chat_id,
            text=UNKNOWN_CALLBACK_TEXT,
            reply_markup=make_reply_keyboard(),
            update_id=update_id,
        )

    async def _run_content_request(
        self,
        *,
        chat_id: int,
        update_id: int,
        request: StreamRequest,
    ) -> None:
        session = self._chat_session(chat_id)
        async with session.lock:
            cancel_event = asyncio.Event()
            current_task = asyncio.current_task()
            if current_task is not None:
                session.active_task = current_task
            session.active_cancel = cancel_event
            session.last_request = request
            try:
                await self._stream_request(
                    chat_id=chat_id,
                    update_id=update_id,
                    request=request,
                    cancel_event=cancel_event,
                )
            except ContentError as ex:
                await self._send_private_reply(
                    chat_id=chat_id,
                    text=str(ex),
                    reply_markup=make_reply_keyboard(),
                    update_id=update_id,
                )
            except Exception:
                self._log.exception(
                    "Unhandled generation error chat_id=%s update_id=%s",
                    chat_id,
                    update_id,
                )
                await self._send_private_reply(
                    chat_id=chat_id,
                    text=GENERIC_ERROR_TEXT,
                    reply_markup=make_reply_keyboard(),
                    update_id=update_id,
                )
            finally:
                if current_task is not None and session.active_task is current_task:
                    session.active_task = None
                session.active_cancel = None

    async def _stream_request(
        self,
        *,
        chat_id: int,
        update_id: int,
        request: StreamRequest,
        cancel_event: asyncio.Event,
    ) -> None:
        draft_id = _draft_id_for_update(
            update_id,
            chat_id,
            f"{request.mode}:{request.prompt}:{request.variant}",
        )
        title = _force_rtl_line(final_title_for_mode(request.mode))
        lines = [_force_rtl_line(line) for line in build_mode_lines(request)]
        final_text = f"{title}\n\n" + "\n".join(lines)

        try:
            await self._client.send_chat_action(chat_id=chat_id, action="typing")
        except BotApiError as ex:
            self._log.warning("sendChatAction failed chat_id=%s: %s", chat_id, ex)
        if self._initial_typing_delay > 0:
            await asyncio.sleep(self._initial_typing_delay)
        if cancel_event.is_set():
            return

        draft_ok = True
        partial_lines: list[str] = []
        for line in lines:
            if cancel_event.is_set():
                return
            partial_lines.append(line)
            partial_text = f"{title}\n\n" + "\n".join(partial_lines)
            if draft_ok:
                try:
                    await self._client.send_message_draft(
                        chat_id=chat_id,
                        draft_id=draft_id,
                        text=partial_text,
                    )
                except BotApiError as ex:
                    draft_ok = False
                    self._log.warning(
                        "sendMessageDraft failed chat_id=%s update_id=%s: %s",
                        chat_id,
                        update_id,
                        ex,
                    )
                    try:
                        await self._client.send_chat_action(chat_id=chat_id, action="typing")
                    except BotApiError:
                        pass
            if self._draft_step_delay > 0:
                await asyncio.sleep(self._draft_step_delay)

        if cancel_event.is_set():
            return

        await self._send_private_reply(
            chat_id=chat_id,
            text=final_text,
            reply_markup=make_result_actions(),
            update_id=update_id,
        )

    async def _stop_active_generation(self, *, chat_id: int, update_id: int) -> None:
        session = self._chat_session(chat_id)
        cancel = session.active_cancel
        task = session.active_task
        if cancel is None or task is None or task.done():
            await self._send_private_reply(
                chat_id=chat_id,
                text=NO_ACTIVE_STREAM_TEXT,
                reply_markup=make_reply_keyboard(),
                update_id=update_id,
            )
            return
        cancel.set()
        await self._send_private_reply(
            chat_id=chat_id,
            text=STOPPED_STREAM_TEXT,
            reply_markup=make_reply_keyboard(),
            update_id=update_id,
        )

    async def _send_menu(self, *, chat_id: int, update_id: int) -> None:
        await self._send_private_reply(
            chat_id=chat_id,
            text=MENU_TEXT,
            reply_markup=make_inline_menu(),
            update_id=update_id,
        )
        await self._send_private_reply(
            chat_id=chat_id,
            text=MENU_KEYBOARD_TEXT,
            reply_markup=make_reply_keyboard(),
            update_id=update_id,
        )

    async def _send_private_reply(
        self,
        *,
        chat_id: int,
        text: str,
        reply_markup: dict[str, Any] | None = None,
        update_id: int | None = None,
    ) -> None:
        try:
            await self._client.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)
        except BotApiError as ex:
            self._log.error(
                "sendMessage failed chat_id=%s update_id=%s: %s",
                chat_id,
                update_id,
                ex,
            )

    async def _send_plain_reply(
        self,
        *,
        chat_id: int,
        text: str,
        update_id: int | None = None,
    ) -> None:
        await self._send_private_reply(chat_id=chat_id, text=text, update_id=update_id)


def _build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(
        description="Run the Telecraft Bot API draft-streaming demo.",
    )


async def _async_main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    token = _need("TELEGRAM_STREAMING_BOT_TOKEN")
    logging.getLogger(__name__).info("Token loaded: yes")
    offset_store = OffsetStore(OFFSET_PATH)
    state = offset_store.load()
    logging.getLogger(__name__).info("Offset loaded: %s", state.next_update_id)
    app = StreamingBotApp(
        BotApiClient(BotApiConfig(token=token)),
        offset_store=offset_store,
    )
    await app.run_forever()


def main(argv: Sequence[str] | None = None) -> int:
    _build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        asyncio.run(_async_main())
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Streaming bot stopped")
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
