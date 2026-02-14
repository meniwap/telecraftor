from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from telecraft.client.entities import EntityCacheError
from telecraft.client.peers import PeerRef
from telecraft.tl.generated.types import InputReplyToMessage, InputReplyToStory

if TYPE_CHECKING:
    from telecraft.client.mtproto import MtprotoClient


@dataclass(frozen=True, slots=True)
class ReplyToMessageRef:
    msg_id: int


@dataclass(frozen=True, slots=True)
class ReplyToStoryRef:
    peer: PeerRef
    story_id: int


def build_input_reply_to_message(msg_id: int) -> InputReplyToMessage:
    return InputReplyToMessage(
        flags=0,
        reply_to_msg_id=int(msg_id),
        top_msg_id=None,
        reply_to_peer_id=None,
        quote_text=None,
        quote_entities=None,
        quote_offset=None,
        monoforum_peer_id=None,
        todo_item_id=None,
    )


async def build_input_reply_to_story(
    raw: MtprotoClient,
    peer: PeerRef,
    story_id: int,
    *,
    timeout: float,
) -> InputReplyToStory:
    resolved = await raw.resolve_peer(peer, timeout=timeout)
    try:
        input_peer = raw.entities.input_peer(resolved)
    except EntityCacheError:
        await raw.prime_entities(limit=200, timeout=timeout)
        input_peer = raw.entities.input_peer(resolved)
    return InputReplyToStory(peer=input_peer, story_id=int(story_id))
