from __future__ import annotations

from apps.streamingbot.story import build_story_lines


def test_streamingbot_story__returns_exact_count() -> None:
    out = build_story_lines("ישיבת צוות", count=7)
    assert len(out) == 7


def test_streamingbot_story__is_deterministic() -> None:
    assert build_story_lines("פגישה", count=7) == build_story_lines("פגישה", count=7)


def test_streamingbot_story__lines_are_numbered() -> None:
    out = build_story_lines("יום עמוס", count=7)
    for idx, line in enumerate(out, start=1):
        assert line.startswith(f"{idx}. ")
