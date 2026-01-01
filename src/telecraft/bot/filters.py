from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from telecraft.bot.events import ChatActionEvent, MemberUpdateEvent, MessageEvent, ReactionEvent

Filter = Callable[[MessageEvent], bool]
ActionFilter = Callable[[ChatActionEvent], bool]
MemberFilter = Callable[[MemberUpdateEvent], bool]
ReactionFilter = Callable[[ReactionEvent], bool]


def all_() -> Filter:
    return lambda _e: True


def text() -> Filter:
    return lambda e: e.text is not None and e.text != ""


def command(name: str) -> Filter:
    def _f(e: MessageEvent) -> bool:
        return e.command == name

    return _f


def private() -> Filter:
    return lambda e: e.is_private


def group() -> Filter:
    return lambda e: e.is_group


def channel() -> Filter:
    return lambda e: e.is_channel


def from_user(*user_ids: int) -> Filter:
    want = {int(x) for x in user_ids}

    def _f(e: MessageEvent) -> bool:
        if e.sender_id is None:
            return False
        return int(e.sender_id) in want

    return _f


def in_peer(peer_type: str, *peer_ids: int) -> Filter:
    want = {int(x) for x in peer_ids}

    def _f(e: MessageEvent) -> bool:
        if e.peer_type != peer_type:
            return False
        if e.peer_id is None:
            return False
        return int(e.peer_id) in want

    return _f


def in_chat(*chat_ids: int) -> Filter:
    return in_peer("chat", *chat_ids)


def in_channel(*channel_ids: int) -> Filter:
    return in_peer("channel", *channel_ids)


def startswith(prefix: str, *, case_sensitive: bool = True) -> Filter:
    p = prefix if case_sensitive else prefix.lower()

    def _f(e: MessageEvent) -> bool:
        t = e.text
        if not t:
            return False
        s = t if case_sensitive else t.lower()
        return s.startswith(p)

    return _f


def contains(substr: str, *, case_sensitive: bool = False) -> Filter:
    q = substr if case_sensitive else substr.lower()

    def _f(e: MessageEvent) -> bool:
        t = e.text
        if not t:
            return False
        s = t if case_sensitive else t.lower()
        return q in s

    return _f


def regex(pattern: str, *, flags: int = 0) -> Filter:
    rx = re.compile(pattern, flags=flags)

    def _f(e: MessageEvent) -> bool:
        t = e.text
        if not t:
            return False
        return rx.search(t) is not None

    return _f


def incoming() -> Filter:
    return lambda e: not e.outgoing


def outgoing() -> Filter:
    return lambda e: e.outgoing


def new_message() -> Filter:
    return lambda e: getattr(e, "kind", "new") == "new"


def edited_message() -> Filter:
    return lambda e: getattr(e, "kind", "new") == "edit"


def has_media() -> Filter:
    def _f(e: MessageEvent) -> bool:
        fn = getattr(e, "has_media", None)
        if callable(fn):
            try:
                return bool(fn())
            except Exception:  # noqa: BLE001
                return False
        media = getattr(getattr(e, "raw", None), "media", None)
        return media is not None

    return _f


def reply_to() -> Filter:
    return lambda e: getattr(e, "reply_to_msg_id", None) is not None


def action_in_peer(peer_type: str, *peer_ids: int) -> ActionFilter:
    want = {int(x) for x in peer_ids}

    def _f(e: ChatActionEvent) -> bool:
        if e.peer_type != peer_type:
            return False
        if e.peer_id is None:
            return False
        return int(e.peer_id) in want

    return _f


def action_in_chat(*chat_ids: int) -> ActionFilter:
    return action_in_peer("chat", *chat_ids)


def action_in_channel(*channel_ids: int) -> ActionFilter:
    return action_in_peer("channel", *channel_ids)


def action_from_user(*user_ids: int) -> ActionFilter:
    want = {int(x) for x in user_ids}

    def _f(e: ChatActionEvent) -> bool:
        if e.sender_id is None:
            return False
        return int(e.sender_id) in want

    return _f


def action_inviter(*user_ids: int) -> ActionFilter:
    want = {int(x) for x in user_ids}

    def _f(e: ChatActionEvent) -> bool:
        if e.inviter_id is None:
            return False
        return int(e.inviter_id) in want

    return _f


def action_pinned_msg(*msg_ids: int) -> ActionFilter:
    want = {int(x) for x in msg_ids}

    def _f(e: ChatActionEvent) -> bool:
        if e.pinned_msg_id is None:
            return False
        return int(e.pinned_msg_id) in want

    return _f


def action_title_contains(substr: str, *, case_sensitive: bool = False) -> ActionFilter:
    q = substr if case_sensitive else substr.lower()

    def _f(e: ChatActionEvent) -> bool:
        t = e.new_title
        if not t:
            return False
        s = t if case_sensitive else t.lower()
        return q in s

    return _f


def member_kind(*kinds: str) -> MemberFilter:
    want = {str(x) for x in kinds}

    def _f(e: MemberUpdateEvent) -> bool:
        return str(getattr(e, "kind", "update")) in want

    return _f


def member_joined() -> MemberFilter:
    return member_kind("join", "invite")


def member_left() -> MemberFilter:
    return member_kind("leave", "kick")


def member_banned() -> MemberFilter:
    return member_kind("ban")


def member_promoted() -> MemberFilter:
    return member_kind("promote")


def member_in_peer(peer_type: str, *peer_ids: int) -> MemberFilter:
    want = {int(x) for x in peer_ids}

    def _f(e: MemberUpdateEvent) -> bool:
        if e.peer_type != peer_type:
            return False
        if e.peer_id is None:
            return False
        return int(e.peer_id) in want

    return _f


def member_in_chat(*chat_ids: int) -> MemberFilter:
    return member_in_peer("chat", *chat_ids)


def member_in_channel(*channel_ids: int) -> MemberFilter:
    return member_in_peer("channel", *channel_ids)


def member_actor(*actor_ids: int) -> MemberFilter:
    want = {int(x) for x in actor_ids}

    def _f(e: MemberUpdateEvent) -> bool:
        if e.actor_id is None:
            return False
        return int(e.actor_id) in want

    return _f


def member_user(*user_ids: int) -> MemberFilter:
    want = {int(x) for x in user_ids}

    def _f(e: MemberUpdateEvent) -> bool:
        if e.user_id is None:
            return False
        return int(e.user_id) in want

    return _f


def action_kind(*kinds: str) -> ActionFilter:
    want = {str(x) for x in kinds}

    def _f(e: ChatActionEvent) -> bool:
        return str(getattr(e, "kind", "other")) in want

    return _f


def reaction_contains(reaction_key: str) -> ReactionFilter:
    def _f(e: ReactionEvent) -> bool:
        try:
            return reaction_key in getattr(e, "counts", {})
        except Exception:  # noqa: BLE001
            return False

    return _f


def reaction_count_gte(reaction_key: str, n: int) -> ReactionFilter:
    want = int(n)

    def _f(e: ReactionEvent) -> bool:
        try:
            fn = getattr(e, "count", None)
            if callable(fn):
                return int(fn(reaction_key)) >= want
            return int(getattr(e, "counts", {}).get(reaction_key, 0)) >= want
        except Exception:  # noqa: BLE001
            return False

    return _f


def action_join() -> ActionFilter:
    return action_kind("join")


def action_leave() -> ActionFilter:
    return action_kind("leave")


def action_pin() -> ActionFilter:
    return action_kind("pin")


def action_title() -> ActionFilter:
    return action_kind("title")


def action_photo() -> ActionFilter:
    return action_kind("photo")


@dataclass(frozen=True, slots=True)
class And:
    a: Filter
    b: Filter

    def __call__(self, e: MessageEvent) -> bool:
        return self.a(e) and self.b(e)


@dataclass(frozen=True, slots=True)
class Or:
    a: Filter
    b: Filter

    def __call__(self, e: MessageEvent) -> bool:
        return self.a(e) or self.b(e)


def and_(a: Filter, b: Filter) -> Filter:
    return And(a=a, b=b)


def or_(a: Filter, b: Filter) -> Filter:
    return Or(a=a, b=b)

