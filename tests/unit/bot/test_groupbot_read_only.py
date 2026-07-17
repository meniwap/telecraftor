from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

from telecraft.bot import PluginLoader, Router, Scheduler
from telecraft.bot.events import MessageEvent
from telecraft.bot.groupbot import (
    GroupBotConfig,
    GroupBotContext,
    GroupBotStorage,
    attach_group_bot_context,
)
from telecraft.client import Peer


class _Raw:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def resolve_peer(self, ref: object, *, timeout: float = 20.0) -> Peer:
        _ = timeout
        value = str(ref)
        if value.startswith("user:"):
            return Peer.user(int(value.split(":", 1)[1]))
        raise ValueError(f"unexpected ref: {ref}")

    async def send_message(
        self,
        peer: object,
        text: str,
        *,
        reply_to_msg_id: int | None = None,
        reply_markup: object | None = None,
    ) -> object:
        _ = (peer, reply_to_msg_id, reply_markup)
        self.sent.append(text)
        return {"ok": True}


class _Messages:
    def __init__(self) -> None:
        self.delete_calls = 0

    async def delete(self, *args: Any, **kwargs: Any) -> object:
        _ = (args, kwargs)
        self.delete_calls += 1
        return {"ok": True}


class _Polls:
    def __init__(self) -> None:
        self.calls = 0

    async def send(self, *args: Any, **kwargs: Any) -> object:
        _ = (args, kwargs)
        self.calls += 1
        return {"ok": True}

    async def send_quiz(self, *args: Any, **kwargs: Any) -> object:
        _ = (args, kwargs)
        self.calls += 1
        return {"ok": True}


class _Admin:
    async def member(self, *args: Any, **kwargs: Any) -> object:
        _ = (args, kwargs)

        class _RegularMember:
            TL_NAME = "channelParticipant"

        return _RegularMember()


class _App:
    def __init__(self) -> None:
        self.raw = _Raw()
        self.messages = _Messages()
        self.polls = _Polls()
        self.admin = _Admin()


def test_groupbot__read_only_blocks_state_and_telegram_mutations(tmp_path: Path) -> None:
    async def _case() -> tuple[int, int, int, int, list[str], bool, bool, bool]:
        app = _App()
        storage = GroupBotStorage(tmp_path / "readonly.sqlite3")
        router = Router()
        ctx = GroupBotContext(
            app=app,  # type: ignore[arg-type]
            router=router,
            scheduler=Scheduler(),
            storage=storage,
            config=GroupBotConfig(
                allowed_peers=["channel:10", "channel:20"],
                admin_user_ids=[1],
                read_only_mode=True,
                flood_message_count=2,
                blocked_keywords=["blocked-token"],
            ),
        )
        ctx.allowed_peer_keys = {"channel:10", "channel:20"}
        attach_group_bot_context(router, ctx)

        apps_dir = Path(__file__).resolve().parents[3] / "apps"
        sys.path.insert(0, str(apps_dir))
        loader = PluginLoader(router=router)
        try:
            await loader.load_path(
                apps_dir / "bot_plugins" / "moderation.py",
                module_name="tc_groupbot_readonly_moderation",
            )
            await loader.load_path(
                apps_dir / "bot_plugins" / "utilities.py",
                module_name="tc_groupbot_readonly_utilities",
            )

            storage.increment_warning(peer_key="channel:10", user_id=2, reason="baseline")
            storage.upsert_scheduled_job(
                name="readonly-job",
                text="must not run",
                interval_seconds=60,
                peer_ref="channel:10",
            )
            storage.upsert_scheduled_job(
                name="other-group-job",
                text="must remain",
                interval_seconds=60,
                peer_ref="channel:20",
            )

            async def dispatch(text: str, *, sender_id: int, msg_id: int) -> None:
                await router.dispatch_message(
                    MessageEvent(
                        client=app.raw,
                        raw=object(),
                        peer_type="channel",
                        peer_id=10,
                        sender_id=sender_id,
                        msg_id=msg_id,
                        text=text,
                    )
                )

            await dispatch("/warn user:2 dry-run", sender_id=1, msg_id=1)
            await dispatch("/unwarn user:2", sender_id=1, msg_id=2)
            await dispatch("/poll Question | A | B", sender_id=1, msg_id=3)
            await dispatch("/quiz Question | A | B | 1", sender_id=1, msg_id=4)
            await dispatch("/jobs", sender_id=1, msg_id=10)
            await dispatch("/unschedule other-group-job", sender_id=1, msg_id=11)
            await dispatch("/unschedule readonly-job", sender_id=1, msg_id=8)
            await dispatch("https://example.invalid", sender_id=3, msg_id=5)
            await dispatch("normal one", sender_id=4, msg_id=6)
            await dispatch("normal two", sender_id=4, msg_id=7)
            await dispatch("normal three", sender_id=4, msg_id=9)

            return (
                storage.get_warning_count(peer_key="channel:10", user_id=2),
                storage.get_warning_count(peer_key="channel:10", user_id=3),
                storage.get_warning_count(peer_key="channel:10", user_id=4),
                app.polls.calls + app.messages.delete_calls,
                list(app.raw.sent),
                storage.get_scheduled_job(name="readonly-job") is None,
                ctx.flood_on_cooldown(peer_key="channel:10", user_id=4),
                storage.get_scheduled_job(name="other-group-job") is not None,
            )
        finally:
            await loader.unload("tc_groupbot_readonly_utilities")
            await loader.unload("tc_groupbot_readonly_moderation")
            if str(apps_dir) in sys.path:
                sys.path.remove(str(apps_dir))
            storage.close()

    (
        user2,
        user3,
        user4,
        mutation_calls,
        replies,
        schedule_removed,
        flood_cooldown,
        other_group_preserved,
    ) = asyncio.run(_case())
    assert (user2, user3, user4) == (1, 0, 0)
    assert mutation_calls == 0
    assert any("[dry-run] warn" in reply for reply in replies)
    assert any("[dry-run] unwarn" in reply for reply in replies)
    assert any("[dry-run] poll" in reply for reply in replies)
    assert any("[dry-run] quiz" in reply for reply in replies)
    assert any("[dry-run] content-violation" in reply for reply in replies)
    assert sum("[dry-run] anti-flood" in reply for reply in replies) == 1
    jobs_reply = next(reply for reply in replies if reply.startswith("משימות מתוזמנות:"))
    assert "readonly-job" in jobs_reply
    assert "other-group-job" not in jobs_reply
    assert any("לא נמצאה משימה בשם `other-group-job`" in reply for reply in replies)
    assert any("readonly-job` הוסרה" in reply for reply in replies)
    assert schedule_removed is True
    assert flood_cooldown is True
    assert other_group_preserved is True
