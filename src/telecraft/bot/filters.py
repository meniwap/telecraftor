from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from telecraft.bot.events import MessageEvent

Filter = Callable[[MessageEvent], bool]


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

