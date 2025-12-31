from __future__ import annotations

import logging
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

    async def run(self) -> None:
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
                continue
            await self.router.dispatch_message(evt)

