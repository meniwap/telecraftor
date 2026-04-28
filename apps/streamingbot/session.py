from __future__ import annotations

import asyncio
from dataclasses import dataclass


@dataclass(slots=True)
class StreamRequest:
    mode: str
    prompt: str
    variant: int = 0


@dataclass(slots=True)
class ChatSession:
    lock: asyncio.Lock
    last_request: StreamRequest | None = None
    active_task: asyncio.Task[None] | None = None
    active_cancel: asyncio.Event | None = None
