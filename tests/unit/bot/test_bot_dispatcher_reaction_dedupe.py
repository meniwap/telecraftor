from __future__ import annotations

import asyncio
from dataclasses import dataclass

from telecraft.bot.dispatcher import Dispatcher
from telecraft.bot.events import ReactionEvent
from telecraft.bot.router import Router


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


def test_dispatcher_reaction_dedupe_allows_legit_changes_on_same_msg_id() -> None:
    seen: list[ReactionEvent] = []
    router = Router()

    @router.on_reaction()
    async def _h(e: ReactionEvent) -> None:
        seen.append(e)

    disp = Dispatcher(client=object(), router=router, ignore_before_start=False)

    async def _run() -> None:
        from collections import deque

        r_seen: set[object] = set()
        r_order = deque(maxlen=4096)

        e1 = ReactionEvent(
            client=object(),
            raw=object(),
            peer_type="chat",
            peer_id=1,
            msg_id=10,
            reactions=FakeMessageReactions(
                results=[FakeReactionCount(reaction=FakeReactionEmoji("❤️"), count=1)],
                recent_reactions=[FakePeerReaction(my=True, reaction=FakeReactionEmoji("❤️"))],
            ),
        )
        e2 = ReactionEvent(
            client=object(),
            raw=object(),
            peer_type="chat",
            peer_id=1,
            msg_id=10,
            reactions=FakeMessageReactions(
                results=[FakeReactionCount(reaction=FakeReactionEmoji("❤️"), count=2)],
                recent_reactions=[FakePeerReaction(my=True, reaction=FakeReactionEmoji("❤️"))],
            ),
        )

        await disp._handle_reaction(  # noqa: SLF001
            e1,
            started_at=0,
            now_ts=999999999,
            seen_reaction=r_seen,  # type: ignore[arg-type]
            seen_reaction_order=r_order,  # type: ignore[arg-type]
            global_bucket=None,
            peer_rate_per_sec=None,
            peer_buckets={},
        )
        await disp._handle_reaction(  # noqa: SLF001
            e2,
            started_at=0,
            now_ts=999999999,
            seen_reaction=r_seen,  # type: ignore[arg-type]
            seen_reaction_order=r_order,  # type: ignore[arg-type]
            global_bucket=None,
            peer_rate_per_sec=None,
            peer_buckets={},
        )

    asyncio.run(_run())
    assert [e.count("❤️") for e in seen] == [1, 2]
