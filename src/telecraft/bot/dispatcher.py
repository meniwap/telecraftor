from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import Any

from telecraft.bot.events import MessageEvent
from telecraft.bot.router import Router

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class Dispatcher:
    """
    Runs the bot loop:
    - reads raw updates from MtprotoClient.recv_update()
    - converts them to MessageEvent when possible
    - calls Router handlers with isolation (exceptions are logged, loop continues)
    """

    client: Any
    router: Router
    ignore_outgoing: bool = True
    ignore_before_start: bool = True
    backlog_grace_seconds: int = 10
    debug: bool = False

    async def run(self) -> None:
        started_at = int(time.time())
        # Dedupe messages by (peer_type, peer_id, msg_id) to avoid echoing the same message twice.
        seen: set[tuple[str, int, int]] = set()
        seen_order: deque[tuple[str, int, int]] = deque(maxlen=4096)

        # Best-effort: populate access_hash cache (enables DM/channel replies).
        prime = getattr(self.client, "prime_entities", None)
        if callable(prime):
            try:
                await prime()
            except Exception as ex:  # noqa: BLE001
                logger.info("prime_entities failed; continuing without priming", exc_info=ex)

        await self.client.start_updates()
        while True:
            upd = await self.client.recv_update()
            evt = MessageEvent.from_update(client=self.client, update=upd)
            if evt is None:
                if self.debug:
                    logger.info(
                        "Skip: unmapped update %s",
                        getattr(upd, "TL_NAME", type(upd).__name__),
                    )
                continue

            # Never react to our own outgoing messages (prevents echo-loops).
            if self.ignore_outgoing and evt.outgoing:
                if self.debug:
                    logger.info("Skip: outgoing message msg_id=%s", evt.msg_id)
                continue

            # Skip backlog/old messages on startup (prevents "echo all history").
            # Telegram dates are unix timestamps (seconds).
            if (
                self.ignore_before_start
                and evt.date is not None
                and evt.date < (started_at - int(self.backlog_grace_seconds))
            ):
                if self.debug:
                    logger.info("Skip: old message date=%s started_at=%s", evt.date, started_at)
                continue

            # Dedupe: sometimes the same message can arrive via different wrappers.
            peer_type: str
            peer_id: int
            if evt.chat_id is not None:
                peer_type, peer_id = "chat", int(evt.chat_id)
            elif evt.channel_id is not None:
                peer_type, peer_id = "channel", int(evt.channel_id)
            elif evt.user_id is not None:
                peer_type, peer_id = "user", int(evt.user_id)
            else:
                peer_type, peer_id = "unknown", 0

            if evt.msg_id is not None:
                key = (peer_type, peer_id, int(evt.msg_id))
                if key in seen:
                    continue
                if len(seen_order) == seen_order.maxlen:
                    old = seen_order.popleft()
                    seen.discard(old)
                seen_order.append(key)
                seen.add(key)

            await self.router.dispatch_message(evt)

