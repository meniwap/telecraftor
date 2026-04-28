from __future__ import annotations

from apps.streamingbot.fortune import build_fortune_lines


def test_streamingbot_fortune__returns_exact_count() -> None:
    out = build_fortune_lines("שבוע עבודה", count=8)
    assert len(out) == 8


def test_streamingbot_fortune__is_deterministic() -> None:
    assert build_fortune_lines("היום שלך", count=8) == build_fortune_lines("היום שלך", count=8)


def test_streamingbot_fortune__lines_are_numbered() -> None:
    out = build_fortune_lines("יום ראשון", count=8)
    for idx, line in enumerate(out, start=1):
        assert line.startswith(f"{idx}. ")
