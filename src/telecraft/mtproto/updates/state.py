from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast

from telecraft.tl.generated.types import UpdatesState as TlUpdatesState


@dataclass(slots=True)
class UpdatesState:
    """
    Durable updates state needed for global and per-channel differences.

    ``channel_pts`` does not participate in equality because Telegram advances
    global and channel message boxes independently.  Callers that need to
    compare or persist the channel cursors must inspect/copy the mapping
    explicitly.
    """

    pts: int
    qts: int
    date: int
    seq: int
    channel_pts: dict[int, int] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_tl(cls, tl: Any) -> UpdatesState:
        if not isinstance(tl, TlUpdatesState):
            raise TypeError(f"Expected updates.state, got: {type(tl).__name__}")
        return cls(
            pts=int(cast(int, tl.pts)),
            qts=int(cast(int, tl.qts)),
            date=int(cast(int, tl.date)),
            seq=int(cast(int, tl.seq)),
        )
