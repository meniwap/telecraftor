from __future__ import annotations

from telecraft.bot import (
    ChatActionEvent,
    ReactionEvent,
    action_from_user,
    action_in_chat,
    action_inviter,
    action_join,
    action_pinned_msg,
    action_title_contains,
    channel,
    command,
    contains,
    edited_message,
    from_user,
    group,
    has_media,
    in_channel,
    in_chat,
    incoming,
    new_message,
    outgoing,
    private,
    reaction_contains,
    reaction_count_gte,
    regex,
    reply_to,
    startswith,
    text,
)
from telecraft.bot.events import MessageEvent


def _e(**kw):
    base = MessageEvent(client=object(), raw=object())
    for k, v in kw.items():
        setattr(base, k, v)
    return base


def _a(**kw):
    base = ChatActionEvent(
        client=object(),
        raw=object(),
        peer_type=None,
        peer_id=None,
        msg_id=None,
        date=None,
        sender_id=None,
        outgoing=False,
    )
    for k, v in kw.items():
        setattr(base, k, v)
    return base


def _r(**kw):
    base = ReactionEvent(
        client=object(),
        raw=object(),
        peer_type=None,
        peer_id=None,
        msg_id=1,
        reactions=None,
    )
    for k, v in kw.items():
        setattr(base, k, v)
    return base


def test_filters_basic_text() -> None:
    assert text()(_e(text="hi")) is True
    assert text()(_e(text="")) is False
    assert text()(_e(text=None)) is False


def test_filters_private_group_channel() -> None:
    assert private()(_e(peer_type="user", peer_id=1)) is True
    assert group()(_e(peer_type="chat", peer_id=1)) is True
    assert channel()(_e(peer_type="channel", peer_id=1)) is True


def test_filters_from_user() -> None:
    f = from_user(1, 2)
    assert f(_e(sender_id=1)) is True
    assert f(_e(sender_id=3)) is False
    assert f(_e(sender_id=None)) is False


def test_filters_in_peer_helpers() -> None:
    assert in_chat(10)(_e(peer_type="chat", peer_id=10)) is True
    assert in_channel(5)(_e(peer_type="channel", peer_id=5)) is True
    assert in_chat(10)(_e(peer_type="chat", peer_id=11)) is False


def test_filters_startswith_contains_regex() -> None:
    e = _e(text="Hello World")
    assert startswith("Hello")(e) is True
    assert startswith("hello", case_sensitive=False)(e) is True
    assert contains("world")(e) is True
    import re

    assert regex(r"w.rld", flags=re.IGNORECASE)(e) is True


def test_filter_command_uses_event_command_property() -> None:
    e = _e(text="/start 123")
    assert command("start")(e) is True
    assert command("help")(e) is False


def test_filters_incoming_outgoing_kind() -> None:
    e = _e(outgoing=False, kind="new")
    assert incoming()(e) is True
    assert outgoing()(e) is False
    assert new_message()(e) is True
    assert edited_message()(e) is False

    e2 = _e(outgoing=True, kind="edit")
    assert incoming()(e2) is False
    assert outgoing()(e2) is True
    assert new_message()(e2) is False
    assert edited_message()(e2) is True


def test_filters_reply_to_and_has_media() -> None:
    class R:
        reply_to_msg_id = 123

    class Raw:
        media = object()
        reply_to = R()

    e = _e(raw=Raw())
    assert reply_to()(e) is True
    assert has_media()(e) is True


def test_action_filters_basic() -> None:
    a = _a(kind="join", peer_type="chat", peer_id=10, sender_id=5, inviter_id=7)
    assert action_join()(a) is True
    assert action_in_chat(10)(a) is True
    assert action_from_user(5)(a) is True
    assert action_inviter(7)(a) is True

    pin = _a(kind="pin", peer_type="chat", peer_id=10, pinned_msg_id=99)
    assert action_pinned_msg(99)(pin) is True

    title = _a(kind="title", peer_type="chat", peer_id=10, new_title="Hello World")
    assert action_title_contains("world")(title) is True


def test_reaction_filters_basic() -> None:
    class ReactionEmoji:
        TL_NAME = "reactionEmoji"

        def __init__(self, emoticon: str) -> None:
            self.emoticon = emoticon

    class ReactionCount:
        def __init__(self, reaction: object, count: int) -> None:
            self.reaction = reaction
            self.count = count

    class MessageReactions:
        def __init__(self) -> None:
            self.results = [
                ReactionCount(reaction=ReactionEmoji("❤️"), count=3),
            ]

    e = _r(reactions=MessageReactions())
    assert reaction_contains("❤️")(e) is True
    assert reaction_count_gte("❤️", 2)(e) is True
    assert reaction_count_gte("❤️", 5)(e) is False


