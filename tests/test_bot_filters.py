from __future__ import annotations

from telecraft.bot import (
    channel,
    command,
    contains,
    from_user,
    group,
    in_channel,
    in_chat,
    private,
    regex,
    startswith,
    text,
)
from telecraft.bot.events import MessageEvent


def _e(**kw):
    base = MessageEvent(client=object(), raw=object())
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


