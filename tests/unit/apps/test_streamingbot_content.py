from __future__ import annotations

import pytest

from apps.streamingbot.content import ContentError, build_mode_lines, final_title_for_mode
from apps.streamingbot.session import StreamRequest


def test_streamingbot_content__build_mode_lines__delegates_per_mode() -> None:
    joke_lines = build_mode_lines(StreamRequest(mode="joke", prompt="קפה"))
    story_lines = build_mode_lines(StreamRequest(mode="story", prompt="פגישה"))
    fortune_lines = build_mode_lines(StreamRequest(mode="fortune", prompt="יום ראשון"))
    battle_lines = build_mode_lines(StreamRequest(mode="battle", prompt="חתול|כלב"))

    assert len(joke_lines) == 10
    assert len(story_lines) == 7
    assert len(fortune_lines) == 8
    assert len(battle_lines) == 8
    assert final_title_for_mode("battle") == "מצב: באטל"


def test_streamingbot_content__unknown_mode_raises_error() -> None:
    with pytest.raises(ContentError):
        build_mode_lines(StreamRequest(mode="unknown", prompt="x"))
