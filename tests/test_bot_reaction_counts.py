from __future__ import annotations

from dataclasses import dataclass

from telecraft.bot.events import ReactionEvent


@dataclass
class FakeReactionEmoji:
    TL_NAME = "reactionEmoji"

    emoticon: str


@dataclass
class FakeReactionCount:
    reaction: object
    count: int


@dataclass
class FakePeerReaction:
    my: bool
    reaction: object


@dataclass
class FakeMessageReactions:
    results: list[object]
    recent_reactions: list[object] | None = None


def test_reaction_event_counts_and_my_reactions() -> None:
    mr = FakeMessageReactions(
        results=[
            FakeReactionCount(reaction=FakeReactionEmoji("❤️"), count=2),
            FakeReactionCount(reaction=FakeReactionEmoji("👍"), count=1),
        ],
        recent_reactions=[
            FakePeerReaction(my=True, reaction=FakeReactionEmoji("❤️")),
            FakePeerReaction(my=False, reaction=FakeReactionEmoji("👍")),
        ],
    )
    e = ReactionEvent(
        client=object(),
        raw=object(),
        peer_type="chat",
        peer_id=1,
        msg_id=1,
        reactions=mr,
    )
    assert e.counts == {"❤️": 2, "👍": 1}
    assert e.total_count == 3
    assert e.my_reactions == ["❤️"]


