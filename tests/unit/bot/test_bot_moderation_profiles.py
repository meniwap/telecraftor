from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
APPS = ROOT / "apps"
if str(APPS) not in sys.path:
    sys.path.insert(0, str(APPS))

from bot_plugins.moderation import build_restrict_rights, try_readd_user  # noqa: E402
from bot_plugins.shared import normalize_restrict_profile, parse_restrict_args  # noqa: E402


class _InviteObj:
    def __init__(self, link: str) -> None:
        self.link = link


class _InviteRes:
    def __init__(self, link: str) -> None:
        self.invite = _InviteObj(link)


class _InvitesOk:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def create(
        self,
        channel_ref: str,
        **kwargs: object,
    ) -> object:
        self.calls.append((channel_ref, kwargs))
        return _InviteRes("https://t.me/+abc123")


class _InvitesFail:
    async def create(
        self,
        channel_ref: str,
        **kwargs: object,
    ) -> object:
        _ = (channel_ref, kwargs)
        raise RuntimeError("BOT_METHOD_INVALID")


class _Chats:
    def __init__(self, invites: object) -> None:
        self.invites = invites


class _App:
    def __init__(self, chats: object) -> None:
        self.chats = chats


def test_parse_restrict_args__supports_profile_and_minutes_order__returns_expected_shape() -> None:
    t1, p1, m1 = parse_restrict_args("user:7 media 9", default_minutes=2)
    assert t1 == "user:7"
    assert p1 == "media"
    assert m1 == 9

    t2, p2, m2 = parse_restrict_args("user:7 3 links", default_minutes=2)
    assert t2 == "user:7"
    assert p2 == "links"
    assert m2 == 3

    t3, p3, m3 = parse_restrict_args("user:7 text", default_minutes=5)
    assert t3 == "user:7"
    assert p3 == "text"
    assert m3 == 5

    t4, p4, m4 = parse_restrict_args("user:7 4", default_minutes=5)
    assert t4 == "user:7"
    assert p4 == "all"
    assert m4 == 4


def test_parse_restrict_args__unknown_profile__raises_value_error() -> None:
    with pytest.raises(ValueError):
        parse_restrict_args("user:7 unknown 1", default_minutes=5)

    with pytest.raises(ValueError):
        parse_restrict_args("user:7 media 0", default_minutes=5)


def test_normalize_restrict_profile__aliases__returns_expected_shape() -> None:
    assert normalize_restrict_profile("full") == "all"
    assert normalize_restrict_profile("photos") == "media"
    assert normalize_restrict_profile("url") == "links"
    assert normalize_restrict_profile("plain") == "text"


def test_build_restrict_rights__profiles_map_to_expected_flags() -> None:
    all_rights = build_restrict_rights(profile="all", until_date=100)
    assert bool(getattr(all_rights, "send_messages", False))
    assert bool(getattr(all_rights, "send_media", False))
    assert bool(getattr(all_rights, "embed_links", False))
    assert bool(getattr(all_rights, "send_plain", False))
    assert int(getattr(all_rights, "until_date", 0)) == 100

    media_rights = build_restrict_rights(profile="media", until_date=101)
    assert bool(getattr(media_rights, "send_media", False))
    assert bool(getattr(media_rights, "send_docs", False))
    assert not bool(getattr(media_rights, "send_plain", False))
    assert int(getattr(media_rights, "until_date", 0)) == 101

    links_rights = build_restrict_rights(profile="links", until_date=102)
    assert bool(getattr(links_rights, "embed_links", False))
    assert not bool(getattr(links_rights, "send_media", False))
    assert not bool(getattr(links_rights, "send_plain", False))

    text_rights = build_restrict_rights(profile="text", until_date=103)
    assert bool(getattr(text_rights, "send_plain", False))
    assert not bool(getattr(text_rights, "send_media", False))
    assert not bool(getattr(text_rights, "embed_links", False))


def test_try_readd_user__success_and_failure_paths__return_expected_shape() -> None:
    async def _case() -> tuple[
        tuple[bool, str | None, str | None],
        tuple[bool, str | None, str | None],
        int,
    ]:
        ok_invites = _InvitesOk()
        ok_app = _App(_Chats(ok_invites))
        fail_app = _App(_Chats(_InvitesFail()))
        ok_result = await try_readd_user(
            app=ok_app,
            channel_ref="channel:123",
            target_ref="user:77",
            target_user_id=77,
            timeout=5.0,
        )
        fail_result = await try_readd_user(
            app=fail_app,
            channel_ref="channel:123",
            target_ref="user:77",
            target_user_id=77,
            timeout=5.0,
        )
        return ok_result, fail_result, len(ok_invites.calls)

    ok_result, fail_result, calls = asyncio.run(_case())
    assert ok_result[0] is True
    assert ok_result[1] == "https://t.me/+abc123"
    assert ok_result[2] is None
    assert fail_result[0] is False
    assert fail_result[1] is None
    assert "BOT_METHOD_INVALID" in str(fail_result[2])
    assert calls == 1
