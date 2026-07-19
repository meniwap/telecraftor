from __future__ import annotations

import pytest

from telecraft.client.peers import (
    is_self_peer_ref,
    normalize_phone,
    normalize_username,
    parse_peer_ref,
)


def test_normalize_username_accepts_at_and_links() -> None:
    assert normalize_username("@Alice") == "alice"
    assert normalize_username("t.me/Alice") == "alice"
    assert normalize_username("https://t.me/Alice") == "alice"
    assert normalize_username("https://t.me/Alice?start=1") == "alice"


def test_parse_peer_ref_user_chat_channel_prefix() -> None:
    assert parse_peer_ref("user:123") == ("user", 123)
    assert parse_peer_ref("chat:9") == ("chat", 9)
    assert parse_peer_ref("channel:77") == ("channel", 77)


def test_parse_peer_ref_phone() -> None:
    assert parse_peer_ref("+1 (555) 123-4567") == "+15551234567"
    assert normalize_phone("1 (555) 123-4567") == "15551234567"
    assert parse_peer_ref("phone:+1 (555) 123-4567") == "+15551234567"


def test_parse_peer_ref_username_fallback() -> None:
    assert parse_peer_ref("@UserName") == "@username"
    assert parse_peer_ref("t.me/UserName") == "@username"


def test_bare_self_aliases_are_not_parsed_as_usernames() -> None:
    assert is_self_peer_ref(" self ")
    assert is_self_peer_ref("ME")
    assert parse_peer_ref(" self ") == "self"
    assert parse_peer_ref("ME") == "me"


def test_explicit_self_usernames_remain_usernames() -> None:
    assert not is_self_peer_ref("@self")
    assert not is_self_peer_ref("@me")
    assert parse_peer_ref("@self") == "@self"
    assert parse_peer_ref("t.me/me") == "@me"


def test_parse_peer_ref_empty_rejected() -> None:
    with pytest.raises(ValueError):
        _ = parse_peer_ref("   ")
