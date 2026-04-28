from __future__ import annotations

from .battle import build_battle_lines
from .fortune import build_fortune_lines
from .jokes import build_joke_lines
from .session import StreamRequest
from .story import build_story_lines

DEFAULT_PROMPTS: dict[str, str] = {
    "joke": "הייטק",
    "story": "יום במשרד",
    "fortune": "היום שלך",
}

_TITLES: dict[str, str] = {
    "joke": "מצב: בדיחות",
    "story": "מצב: סיפור",
    "fortune": "מצב: תחזית",
    "battle": "מצב: באטל",
}


class ContentError(RuntimeError):
    """Raised when a content request cannot be built."""


def default_prompt_for_mode(mode: str) -> str:
    try:
        return DEFAULT_PROMPTS[mode]
    except KeyError as exc:
        raise ContentError(f"Unknown mode: {mode}") from exc


def build_mode_lines(request: StreamRequest) -> list[str]:
    mode = request.mode
    prompt = request.prompt
    variant = request.variant
    if mode == "joke":
        return build_joke_lines(prompt, count=10, variant=variant)
    if mode == "story":
        return build_story_lines(prompt, count=7, variant=variant)
    if mode == "fortune":
        return build_fortune_lines(prompt, count=8, variant=variant)
    if mode == "battle":
        left, sep, right = prompt.partition("|")
        if not sep or not left.strip() or not right.strip():
            raise ContentError("שימוש: /battle חתול | כלב")
        return build_battle_lines(left.strip(), right.strip(), count=8, variant=variant)
    raise ContentError(f"Unknown mode: {mode}")


def final_title_for_mode(mode: str) -> str:
    try:
        return _TITLES[mode]
    except KeyError as exc:
        raise ContentError(f"Unknown mode: {mode}") from exc
