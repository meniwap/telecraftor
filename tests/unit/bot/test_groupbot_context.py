from __future__ import annotations

import asyncio

from telecraft.bot import Router, Scheduler
from telecraft.bot.groupbot.config import GroupBotConfig
from telecraft.bot.groupbot.context import GroupBotContext, parse_peer_key
from telecraft.bot.groupbot.storage import GroupBotStorage


class _Messages:
    async def send(self, peer: str, text: str, *, timeout: float = 20.0) -> object:
        _ = (peer, text, timeout)
        return {"ok": True}


class _Raw:
    async def resolve_peer(self, ref: str, *, timeout: float = 20.0):  # type: ignore[no-untyped-def]
        _ = timeout
        if ref == "@demo":
            class _P:
                peer_type = "channel"
                peer_id = 321

            return _P()
        raise RuntimeError("unknown peer")


class _Admin:
    async def member(self, channel: str, user: object, *, timeout: float = 20.0):  # type: ignore[no-untyped-def]
        _ = (channel, user, timeout)
        class _M:
            TL_NAME = "channelParticipantAdmin"

        return _M()


class _Client:
    def __init__(self) -> None:
        self.raw = _Raw()
        self.messages = _Messages()
        self.admin = _Admin()


class _PeerInvalidError(Exception):
    def __init__(self) -> None:
        self.message = "PEER_ID_INVALID"
        super().__init__(self.message)


class _RawWithPrime(_Raw):
    def __init__(self) -> None:
        super().__init__()
        self.prime_calls: list[object] = []

    async def _prime_entities_for_reply(  # type: ignore[no-untyped-def]
        self,
        *,
        want,
        timeout: float = 20.0,
    ) -> None:
        _ = timeout
        self.prime_calls.append(want)


class _RetryAdmin:
    def __init__(self) -> None:
        self.calls = 0

    async def member(self, channel: str, user: object, *, timeout: float = 20.0):  # type: ignore[no-untyped-def]
        _ = (channel, user, timeout)
        self.calls += 1
        if self.calls == 1:
            raise _PeerInvalidError()

        class _M:
            TL_NAME = "channelParticipantCreator"

        return _M()


class _ClientRetry:
    def __init__(self) -> None:
        self.raw = _RawWithPrime()
        self.messages = _Messages()
        self.admin = _RetryAdmin()


def test_groupbot_context__peer_key_and_flood__returns_expected_shape(tmp_path) -> None:  # type: ignore[no-untyped-def]
    storage = GroupBotStorage(tmp_path / "db.sqlite3")
    try:
        ctx = GroupBotContext(
            app=_Client(),  # type: ignore[arg-type]
            router=Router(),
            scheduler=Scheduler(),
            storage=storage,
            config=GroupBotConfig(),
            timeout=5.0,
        )
        assert ctx.peer_key("channel", 123) == "channel:123"
        assert parse_peer_key("channel:123") == "channel:123"
        assert parse_peer_key("bad") is None

        n1 = ctx.track_flood(peer_key="channel:123", user_id=9, now=0.0)
        n2 = ctx.track_flood(peer_key="channel:123", user_id=9, now=1.0)
        assert n1 == 1
        assert n2 == 2
    finally:
        storage.close()


def test_groupbot_context__is_admin_retry_after_peer_invalid__returns_true(tmp_path) -> None:  # type: ignore[no-untyped-def]
    async def _case() -> tuple[bool, int, int, bool]:
        storage = GroupBotStorage(tmp_path / "retry.sqlite3")
        try:
            client = _ClientRetry()
            ctx = GroupBotContext(
                app=client,  # type: ignore[arg-type]
                router=Router(),
                scheduler=Scheduler(),
                storage=storage,
                config=GroupBotConfig(),
                timeout=5.0,
            )
            first = await ctx.is_admin(peer_type="channel", peer_id=321, user_id=77)
            second = await ctx.is_admin(peer_type="channel", peer_id=321, user_id=77)
            calls = int(client.admin.calls)
            prime_calls = len(client.raw.prime_calls)
            return first, calls, prime_calls, second
        finally:
            storage.close()

    first, calls, prime_calls, second = asyncio.run(_case())
    assert first is True
    assert calls == 2
    assert prime_calls == 2
    assert second is True
