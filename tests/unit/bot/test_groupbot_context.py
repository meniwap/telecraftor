from __future__ import annotations

import asyncio

import pytest

from apps.group_bot import (
    _hydrate_schedules,
    _install_scope_middlewares,
    _preflight_plugin_paths,
)
from telecraft.bot import Router, Scheduler
from telecraft.bot.events import (
    InlineQueryEvent,
    MessageEvent,
    PrecheckoutQueryEvent,
    ShippingQueryEvent,
)
from telecraft.bot.groupbot.config import (
    GroupBotConfig,
    GroupBotConfigurationError,
    ScheduledAnnouncement,
)
from telecraft.bot.groupbot.context import GroupBotContext, parse_peer_key
from telecraft.bot.groupbot.storage import GroupBotStorage


class _Messages:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send(self, peer: str, text: str, *, timeout: float = 20.0) -> object:
        _ = timeout
        self.sent.append((peer, text))
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


class _CaptureScheduler:
    def __init__(self) -> None:
        self.jobs: dict[str, object] = {}
        self.callables: dict[str, object] = {}

    def every(  # type: ignore[no-untyped-def]
        self,
        interval_seconds,
        fn,
        *,
        name=None,
        run_immediately=False,
    ):
        _ = (interval_seconds, run_immediately)
        assert isinstance(name, str)
        self.jobs[name] = object()
        self.callables[name] = fn
        return self.jobs[name]

    async def cancel(self, name: str) -> bool:
        existed = name in self.jobs
        self.jobs.pop(name, None)
        self.callables.pop(name, None)
        return existed


class _PeerInvalidError(Exception):
    def __init__(self) -> None:
        self.message = "PEER_ID_INVALID"
        super().__init__(self.message)


def test_groupbot_plugins__preflight_rejects_missing_and_invalid_files(tmp_path) -> None:
    missing = tmp_path / "missing.py"
    with pytest.raises(FileNotFoundError, match="Plugin file not found"):
        _preflight_plugin_paths([missing])

    invalid = tmp_path / "invalid.py"
    invalid.write_text("def broken(:\n", encoding="utf-8")
    with pytest.raises(SyntaxError):
        _preflight_plugin_paths([invalid])

    valid = tmp_path / "valid.py"
    valid.write_text("async def setup(router):\n    return None\n", encoding="utf-8")
    _preflight_plugin_paths([valid])


def test_groupbot_scope__guards_inline_and_payment_queries(tmp_path) -> None:
    async def _case() -> tuple[list[str], list[str]]:
        storage = GroupBotStorage(tmp_path / "query-scope.sqlite3")
        router = Router()
        ctx = GroupBotContext(
            app=_Client(),  # type: ignore[arg-type]
            router=router,
            scheduler=Scheduler(),
            storage=storage,
            config=GroupBotConfig(allowed_peers=["channel:10"]),
        )
        ctx.allowed_peer_keys = {"channel:10"}
        _install_scope_middlewares(router, ctx=ctx)
        handled: list[str] = []

        @router.on_inline_query()
        async def _inline(_event: InlineQueryEvent) -> None:
            handled.append("inline")

        @router.on_shipping_query()
        async def _shipping(_event: ShippingQueryEvent) -> None:
            handled.append("shipping")

        @router.on_precheckout_query()
        async def _precheckout(_event: PrecheckoutQueryEvent) -> None:
            handled.append("precheckout")

        async def _dispatch_queries() -> None:
            await router.dispatch_inline_query(
                InlineQueryEvent(
                    client=object(),
                    raw=object(),
                    query_id=1,
                    user_id=99,
                    query="query",
                    offset=None,
                    geo=None,
                    peer_type=None,
                )
            )
            await router.dispatch_shipping_query(
                ShippingQueryEvent(
                    client=object(),
                    raw=object(),
                    query_id=2,
                    user_id=99,
                    payload=None,
                    shipping_address=None,
                )
            )
            await router.dispatch_precheckout_query(
                PrecheckoutQueryEvent(
                    client=object(),
                    raw=object(),
                    query_id=3,
                    user_id=99,
                    payload=None,
                    currency=None,
                    total_amount=None,
                    info=None,
                    shipping_option_id=None,
                )
            )

        try:
            await _dispatch_queries()
            denied = list(handled)
            ctx.allowed_peer_keys.add("user:99")
            await _dispatch_queries()
            return denied, handled
        finally:
            storage.close()

    assert asyncio.run(_case()) == ([], ["inline", "shipping", "precheckout"])


def test_groupbot_scope__guards_conversation_waiters(tmp_path) -> None:
    async def _case() -> tuple[bool, int | None]:
        storage = GroupBotStorage(tmp_path / "conversation-scope.sqlite3")
        router = Router()
        ctx = GroupBotContext(
            app=_Client(),  # type: ignore[arg-type]
            router=router,
            scheduler=Scheduler(),
            storage=storage,
            config=GroupBotConfig(allowed_peers=["channel:10"]),
        )
        ctx.allowed_peer_keys = {"channel:10"}
        _install_scope_middlewares(router, ctx=ctx)
        try:
            waiter = asyncio.create_task(router.wait_for_message(timeout=1.0))
            await asyncio.sleep(0)
            await router.dispatch_message(
                MessageEvent(
                    client=object(),
                    raw=object(),
                    peer_type="channel",
                    peer_id=20,
                    sender_id=7,
                    msg_id=1,
                    text="outside scope",
                )
            )
            rejected_outside = not waiter.done()
            await router.dispatch_message(
                MessageEvent(
                    client=object(),
                    raw=object(),
                    peer_type="channel",
                    peer_id=10,
                    sender_id=7,
                    msg_id=2,
                    text="inside scope",
                )
            )
            return rejected_outside, (await waiter).msg_id
        finally:
            storage.close()

    assert asyncio.run(_case()) == (True, 2)


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


def test_groupbot_context__scope_defaults_fail_closed(tmp_path) -> None:  # type: ignore[no-untyped-def]
    async def _case() -> None:
        storage = GroupBotStorage(tmp_path / "scope.sqlite3")
        try:
            ctx = GroupBotContext(
                app=_Client(),  # type: ignore[arg-type]
                router=Router(),
                scheduler=Scheduler(),
                storage=storage,
                config=GroupBotConfig(),
                timeout=5.0,
            )
            assert ctx.is_peer_allowed("channel", 321) is False
            with pytest.raises(GroupBotConfigurationError, match="allowed_peers"):
                await ctx.resolve_allowed_peer_keys()
        finally:
            storage.close()

    asyncio.run(_case())


def test_groupbot_context__allow_all_requires_explicit_opt_in(tmp_path) -> None:  # type: ignore[no-untyped-def]
    async def _case() -> None:
        storage = GroupBotStorage(tmp_path / "allow-all.sqlite3")
        try:
            ctx = GroupBotContext(
                app=_Client(),  # type: ignore[arg-type]
                router=Router(),
                scheduler=Scheduler(),
                storage=storage,
                config=GroupBotConfig(allow_all_peers=True),
                timeout=5.0,
            )
            assert await ctx.resolve_allowed_peer_keys() == set()
            assert ctx.is_peer_allowed("channel", 321) is True
        finally:
            storage.close()

    asyncio.run(_case())


def test_groupbot_context__remove_schedule_cleans_runtime_and_storage(tmp_path) -> None:  # type: ignore[no-untyped-def]
    async def _case() -> tuple[bool, bool, int, int]:
        storage = GroupBotStorage(tmp_path / "schedule.sqlite3")
        scheduler = Scheduler()
        try:
            ctx = GroupBotContext(
                app=_Client(),  # type: ignore[arg-type]
                router=Router(),
                scheduler=scheduler,
                storage=storage,
                config=GroupBotConfig(allowed_peers=["channel:321"]),
                timeout=5.0,
            )
            await ctx.resolve_allowed_peer_keys()
            await ctx.register_or_update_schedule(
                name="test-job",
                text="hello",
                interval_seconds=60,
                peer_ref="channel:321",
            )
            first = await ctx.remove_schedule("test-job")
            second = await ctx.remove_schedule("test-job")
            return (
                first,
                second,
                len(storage.list_scheduled_jobs(enabled_only=False)),
                len(scheduler.jobs),
            )
        finally:
            await scheduler.stop()
            storage.close()

    first, second, stored_count, runtime_count = asyncio.run(_case())
    assert first is True
    assert second is False
    assert stored_count == 0
    assert runtime_count == 0


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


def test_groupbot_context__read_only_corruption_falls_back_to_safe_default(tmp_path) -> None:  # type: ignore[no-untyped-def]
    storage = GroupBotStorage(tmp_path / "corrupt-readonly.sqlite3")
    try:
        ctx = GroupBotContext(
            app=_Client(),  # type: ignore[arg-type]
            router=Router(),
            scheduler=Scheduler(),
            storage=storage,
            config=GroupBotConfig(read_only_mode=True),
        )
        storage.set_group_setting(
            peer_key="channel:321",
            key="read_only_mode",
            value="corrupt-value",
        )
        assert ctx.get_peer_read_only("channel:321") is True

        storage.set_group_setting(
            peer_key="channel:321",
            key="read_only_mode",
            value=7,
        )
        assert ctx.get_peer_read_only("channel:321") is True
    finally:
        storage.close()


def test_groupbot_context__scheduled_job_enforces_read_only_and_scope(tmp_path) -> None:  # type: ignore[no-untyped-def]
    async def _case() -> tuple[list[tuple[str, str]], bool]:
        storage = GroupBotStorage(tmp_path / "schedule-safety.sqlite3")
        scheduler = _CaptureScheduler()
        client = _Client()
        try:
            ctx = GroupBotContext(
                app=client,  # type: ignore[arg-type]
                router=Router(),
                scheduler=scheduler,  # type: ignore[arg-type]
                storage=storage,
                config=GroupBotConfig(
                    allowed_peers=["channel:321"],
                    read_only_mode=True,
                ),
            )
            await ctx.resolve_allowed_peer_keys()
            await ctx.register_or_update_schedule(
                name="safe-job",
                text="hello",
                interval_seconds=60,
                peer_ref="channel:321",
            )
            runner = scheduler.callables["announcement:safe-job"]
            await runner()  # type: ignore[operator]
            assert client.messages.sent == []

            ctx.set_peer_read_only("channel:321", False)
            await runner()  # type: ignore[operator]

            storage.upsert_scheduled_job(
                name="outside-job",
                text="blocked",
                interval_seconds=60,
                peer_ref="channel:999",
            )
            outside = storage.get_scheduled_job(name="outside-job")
            assert outside is not None
            scheduled = await ctx.ensure_schedule(outside)
            return list(client.messages.sent), scheduled
        finally:
            storage.close()

    sent, outside_scheduled = asyncio.run(_case())
    assert sent == [("channel:321", "hello")]
    assert outside_scheduled is False


def test_groupbot_context__schedule_update_replaces_runtime_closure(tmp_path) -> None:  # type: ignore[no-untyped-def]
    async def _case() -> list[tuple[str, str]]:
        storage = GroupBotStorage(tmp_path / "schedule-update.sqlite3")
        scheduler = _CaptureScheduler()
        client = _Client()
        try:
            ctx = GroupBotContext(
                app=client,  # type: ignore[arg-type]
                router=Router(),
                scheduler=scheduler,  # type: ignore[arg-type]
                storage=storage,
                config=GroupBotConfig(
                    allowed_peers=["channel:321"],
                    read_only_mode=False,
                ),
            )
            await ctx.resolve_allowed_peer_keys()
            await ctx.register_or_update_schedule(
                name="replace-me",
                text="old",
                interval_seconds=60,
                peer_ref="channel:321",
            )
            await ctx.register_or_update_schedule(
                name="replace-me",
                text="new",
                interval_seconds=120,
                peer_ref="channel:321",
            )
            runner = scheduler.callables["announcement:replace-me"]
            await runner()  # type: ignore[operator]
            return list(client.messages.sent)
        finally:
            storage.close()

    assert asyncio.run(_case()) == [("channel:321", "new")]


def test_groupbot_context__invalid_schedule_update_preserves_existing_runtime(tmp_path) -> None:  # type: ignore[no-untyped-def]
    async def _case() -> tuple[bool, str, int]:
        storage = GroupBotStorage(tmp_path / "invalid-schedule-update.sqlite3")
        scheduler = _CaptureScheduler()
        try:
            ctx = GroupBotContext(
                app=_Client(),  # type: ignore[arg-type]
                router=Router(),
                scheduler=scheduler,  # type: ignore[arg-type]
                storage=storage,
                config=GroupBotConfig(
                    allowed_peers=["channel:321"],
                    read_only_mode=False,
                ),
            )
            await ctx.resolve_allowed_peer_keys()
            await ctx.register_or_update_schedule(
                name="keep-me",
                text="old",
                interval_seconds=60,
                peer_ref="channel:321",
            )
            original_runner = scheduler.callables["announcement:keep-me"]
            with pytest.raises(ValueError, match="greater than zero"):
                await ctx.register_or_update_schedule(
                    name="keep-me",
                    text="new",
                    interval_seconds=0,
                    peer_ref="channel:321",
                )
            job = storage.get_scheduled_job(name="keep-me")
            assert job is not None
            return (
                scheduler.callables["announcement:keep-me"] is original_runner,
                job.text,
                job.interval_seconds,
            )
        finally:
            storage.close()

    assert asyncio.run(_case()) == (True, "old", 60)


def test_groupbot_context__config_unschedule_survives_hydration(tmp_path) -> None:  # type: ignore[no-untyped-def]
    async def _case() -> tuple[bool, bool, str, int, int]:
        storage = GroupBotStorage(tmp_path / "config-unschedule.sqlite3")
        scheduler = _CaptureScheduler()
        try:
            ctx = GroupBotContext(
                app=_Client(),  # type: ignore[arg-type]
                router=Router(),
                scheduler=scheduler,  # type: ignore[arg-type]
                storage=storage,
                config=GroupBotConfig(
                    allowed_peers=["channel:321"],
                    read_only_mode=False,
                    announcements=[
                        ScheduledAnnouncement(
                            name="configured",
                            text="hello",
                            every_seconds=60,
                            peer="channel:321",
                        )
                    ],
                ),
            )
            await ctx.resolve_allowed_peer_keys()
            await _hydrate_schedules(ctx)
            assert "announcement:configured" in scheduler.jobs
            assert await ctx.remove_schedule("configured") is True
            await _hydrate_schedules(ctx)
            ctx.config.announcements = []
            await _hydrate_schedules(ctx)
            ctx.config.announcements = [
                ScheduledAnnouncement(
                    name="configured",
                    text="hello again",
                    every_seconds=120,
                    peer="channel:321",
                )
            ]
            await _hydrate_schedules(ctx)
            job = storage.get_scheduled_job(name="configured")
            assert job is not None
            return (
                job.enabled,
                job.suppressed,
                job.text,
                job.interval_seconds,
                len(scheduler.jobs),
            )
        finally:
            storage.close()

    assert asyncio.run(_case()) == (False, True, "hello again", 120, 0)


def test_groupbot_context__basic_chat_admin_is_resolved_from_participants(tmp_path) -> None:  # type: ignore[no-untyped-def]
    class _Participant:
        TL_NAME = "chatParticipantAdmin"
        user_id = 77

    class _Participants:
        participants = [_Participant()]

    class _FullChat:
        participants = _Participants()

    class _Info:
        full_chat = _FullChat()

    class _Profile:
        async def chat_info(self, peer: str, *, timeout: float = 20.0) -> object:
            assert (peer, timeout) == ("chat:55", 5.0)
            return _Info()

    client = _Client()
    client.profile = _Profile()  # type: ignore[attr-defined]
    storage = GroupBotStorage(tmp_path / "basic-chat-admin.sqlite3")
    try:
        ctx = GroupBotContext(
            app=client,  # type: ignore[arg-type]
            router=Router(),
            scheduler=Scheduler(),
            storage=storage,
            config=GroupBotConfig(),
            timeout=5.0,
        )
        assert asyncio.run(ctx.is_admin(peer_type="chat", peer_id=55, user_id=77)) is True
    finally:
        storage.close()
