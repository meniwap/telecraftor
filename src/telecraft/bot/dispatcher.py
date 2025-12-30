from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from telecraft.bot.events import MessageEvent
from telecraft.bot.router import Router


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
        await self.client.start_updates()
        while True:
            upd = await self.client.recv_update()
            evt = MessageEvent.from_update(client=self.client, update=upd)
            if evt is None:
                continue
            await self.router.dispatch_message(evt)

