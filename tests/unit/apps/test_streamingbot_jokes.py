from __future__ import annotations

from apps.streamingbot.jokes import build_joke_lines


def test_streamingbot_jokes__build_joke_lines__returns_exact_count() -> None:
    out = build_joke_lines("ספר לי משהו מצחיק", count=10)
    assert len(out) == 10


def test_streamingbot_jokes__build_joke_lines__lines_are_non_empty_and_numbered() -> None:
    out = build_joke_lines("בדיחות על קוד", count=10)
    for idx, line in enumerate(out, start=1):
        assert line
        assert line.startswith(f"{idx}. ")


def test_streamingbot_jokes__build_joke_lines__is_deterministic_for_same_prompt() -> None:
    a = build_joke_lines("אותו פרומפט", count=10)
    b = build_joke_lines("אותו פרומפט", count=10)
    assert a == b
