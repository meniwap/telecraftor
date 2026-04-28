from __future__ import annotations

from dataclasses import dataclass

from .content import default_prompt_for_mode
from .session import StreamRequest

UNKNOWN_COMMAND_TEXT = "פקודה לא מוכרת. כתוב /help או /menu."
BATTLE_USAGE_TEXT = "שימוש: /battle חתול | כלב"
BATTLE_BUTTON_TEXT = "כתוב: /battle חתול | כלב"

_REPLY_KEYBOARD_ALIASES = {
    "בדיחות": "/joke",
    "סיפור": "/story",
    "תחזית": "/fortune",
    "עזרה": "/help",
    "עצור": "/stop",
}


@dataclass(slots=True)
class ParsedCommand:
    kind: str
    request: StreamRequest | None = None
    text: str | None = None


def _normalize_command_name(raw: str) -> str:
    command = raw.split("@", 1)[0]
    return command.lower()


def _make_request(mode: str, prompt: str | None, *, variant: int = 0) -> StreamRequest:
    normalized_prompt = (prompt or "").strip()
    if not normalized_prompt:
        normalized_prompt = default_prompt_for_mode(mode)
    return StreamRequest(mode=mode, prompt=normalized_prompt, variant=variant)


def parse_text(text: str) -> ParsedCommand:
    stripped = text.strip()
    if not stripped:
        return ParsedCommand(kind="error", text=UNKNOWN_COMMAND_TEXT)

    if stripped == "באטל":
        return ParsedCommand(kind="error", text=BATTLE_BUTTON_TEXT)

    stripped = _REPLY_KEYBOARD_ALIASES.get(stripped, stripped)
    if not stripped.startswith("/"):
        return ParsedCommand(kind="content", request=_make_request("joke", stripped))

    head, _, tail = stripped.partition(" ")
    command = _normalize_command_name(head)
    args = tail.strip()

    if command == "/start":
        return ParsedCommand(kind="start")
    if command == "/help":
        return ParsedCommand(kind="help")
    if command == "/menu":
        return ParsedCommand(kind="menu")
    if command == "/stop":
        return ParsedCommand(kind="stop")
    if command == "/joke":
        return ParsedCommand(kind="content", request=_make_request("joke", args))
    if command == "/story":
        return ParsedCommand(kind="content", request=_make_request("story", args))
    if command == "/fortune":
        return ParsedCommand(kind="content", request=_make_request("fortune", args))
    if command == "/battle":
        left, sep, right = args.partition("|")
        if not sep or not left.strip() or not right.strip():
            return ParsedCommand(kind="error", text=BATTLE_USAGE_TEXT)
        return ParsedCommand(
            kind="content",
            request=StreamRequest(mode="battle", prompt=f"{left.strip()}|{right.strip()}"),
        )
    return ParsedCommand(kind="error", text=UNKNOWN_COMMAND_TEXT)
