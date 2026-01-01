from __future__ import annotations

from dataclasses import dataclass

from telecraft.bot.events import ReactionEvent


@dataclass
class FakeReactionEmoji:
    TL_NAME = "reactionEmoji"

    emoticon: str | bytes


@dataclass
class FakeReactionCount:
    reaction: object
    count: int
    chosen_order: int | None = None


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


def test_reaction_event_decodes_bytes_emoticon_from_codec() -> None:
    mr = FakeMessageReactions(
        results=[
            FakeReactionCount(reaction=FakeReactionEmoji("❤️".encode()), count=2),
        ],
        recent_reactions=[
            FakePeerReaction(my=True, reaction=FakeReactionEmoji("❤️".encode())),
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
    assert e.counts == {"❤️": 2}
    assert e.my_reactions == ["❤️"]


def test_reaction_event_my_reactions_fallbacks_to_chosen_order() -> None:
    # Simulate servers that do not include recent_reactions in updateMessageReactions,
    # but do set chosen_order on ReactionCount for user's reactions.
    mr = FakeMessageReactions(
        results=[
            FakeReactionCount(reaction=FakeReactionEmoji("👍"), count=10, chosen_order=None),
            FakeReactionCount(reaction=FakeReactionEmoji("❤️"), count=2, chosen_order=7),
            FakeReactionCount(reaction=FakeReactionEmoji("🔥"), count=1, chosen_order=9),
        ],
        recent_reactions=None,
    )
    e = ReactionEvent(
        client=object(),
        raw=object(),
        peer_type="chat",
        peer_id=1,
        msg_id=1,
        reactions=mr,
    )
    assert e.my_reactions == ["❤️", "🔥"]


