from __future__ import annotations

from apps.streamingbot.commands import BATTLE_BUTTON_TEXT, BATTLE_USAGE_TEXT, parse_text


def test_streamingbot_commands__parse_text__joke_command_parses_request() -> None:
    parsed = parse_text("/joke משהו")
    assert parsed.kind == "content"
    assert parsed.request is not None
    assert parsed.request.mode == "joke"
    assert parsed.request.prompt == "משהו"


def test_streamingbot_commands__parse_text__plain_text_defaults_to_joke_mode() -> None:
    parsed = parse_text("ספר משהו")
    assert parsed.kind == "content"
    assert parsed.request is not None
    assert parsed.request.mode == "joke"
    assert parsed.request.prompt == "ספר משהו"


def test_streamingbot_commands__parse_text__battle_parses_both_operands() -> None:
    parsed = parse_text("/battle חתול | כלב")
    assert parsed.kind == "content"
    assert parsed.request is not None
    assert parsed.request.mode == "battle"
    assert parsed.request.prompt == "חתול|כלב"


def test_streamingbot_commands__parse_text__malformed_battle_returns_usage_error() -> None:
    parsed = parse_text("/battle חתול")
    assert parsed.kind == "error"
    assert parsed.text == BATTLE_USAGE_TEXT


def test_streamingbot_commands__parse_text__reply_keyboard_tokens_map_correctly() -> None:
    parsed = parse_text("בדיחות")
    assert parsed.kind == "content"
    assert parsed.request is not None
    assert parsed.request.mode == "joke"

    battle = parse_text("באטל")
    assert battle.kind == "error"
    assert battle.text == BATTLE_BUTTON_TEXT
