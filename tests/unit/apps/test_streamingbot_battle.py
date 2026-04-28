from __future__ import annotations

from apps.streamingbot.battle import build_battle_lines


def test_streamingbot_battle__returns_exact_count() -> None:
    out = build_battle_lines("חתול", "כלב", count=8)
    assert len(out) == 8


def test_streamingbot_battle__contains_both_operands() -> None:
    out = build_battle_lines("חתול", "כלב", count=8)
    joined = " ".join(out)
    assert "חתול" in joined
    assert "כלב" in joined


def test_streamingbot_battle__is_deterministic() -> None:
    assert build_battle_lines("קפה", "תה", count=8) == build_battle_lines("קפה", "תה", count=8)
