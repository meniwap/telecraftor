from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, cast

from telecraft.mtproto.updates.state import UpdatesState
from telecraft.tl.generated.functions import UpdatesGetDifference, UpdatesGetState
from telecraft.tl.generated.types import (
    Updates,
    UpdatesCombined,
    UpdatesDifference,
    UpdatesDifferenceEmpty,
    UpdatesDifferenceSlice,
    UpdatesDifferenceTooLong,
    UpdateShort,
    UpdateShortChatMessage,
    UpdateShortMessage,
    UpdatesTooLong,
)
from telecraft.tl.generated.types import (
    UpdatesState as TlUpdatesState,
)

logger = logging.getLogger(__name__)


class UpdatesEngineError(Exception):
    pass


@dataclass(slots=True)
class AppliedUpdates:
    updates: list[Any]
    new_messages: list[Any]
    users: list[Any]
    chats: list[Any]


class UpdatesEngine:
    """
    Minimal MTProto updates engine:
    - Initializes state with updates.getState
    - Applies incoming updates objects, detecting simple pts gaps
    - Fills gaps using updates.getDifference (handles slice/tooLong)

    This is intentionally minimal (no channel difference, no entity cache yet).
    """

    def __init__(
        self,
        *,
        invoke_api: Callable[[Any], Awaitable[Any]],
        pts_total_limit: int | None = None,
    ) -> None:
        self._invoke_api = invoke_api
        self._pts_total_limit = pts_total_limit
        self.state: UpdatesState | None = None

    async def initialize(self, *, initial_state: UpdatesState | None = None) -> UpdatesState:
        """
        Initialize updates engine state.

        - If initial_state is provided (e.g. loaded from disk), it will be used directly.
        - Otherwise we fetch updates.getState from the server.
        """
        if initial_state is not None:
            self.state = initial_state
            return self.state
        res = await self._invoke_api(UpdatesGetState())
        self.state = UpdatesState.from_tl(res)
        return self.state

    async def apply(self, obj: Any) -> AppliedUpdates:
        if self.state is None:
            raise UpdatesEngineError("Updates engine not initialized (call initialize())")

        # updatesTooLong: must fetch difference.
        if isinstance(obj, UpdatesTooLong):
            return await self._fetch_difference()

        # updateShortMessage / updateShortChatMessage: contains pts/pts_count.
        if isinstance(obj, (UpdateShortMessage, UpdateShortChatMessage)):
            pts = int(cast(int, obj.pts))
            pts_count = int(cast(int, obj.pts_count))
            if pts != self.state.pts + pts_count:
                logger.info(
                    "PTS gap detected (have=%s, got=%s, count=%s); fetching difference",
                    self.state.pts,
                    pts,
                    pts_count,
                )
                return await self._fetch_difference()
            self.state.pts = pts
            self.state.date = int(cast(int, obj.date))
            return AppliedUpdates(updates=[obj], new_messages=[], users=[], chats=[])

        # updateShort: wraps a single Update + date.
        if isinstance(obj, UpdateShort):
            self.state.date = int(cast(int, obj.date))
            inner = obj.update
            return await self.apply(inner)

        # updates / updatesCombined: list of updates, plus seq+date.
        if isinstance(obj, (Updates, UpdatesCombined)):
            self.state.date = int(cast(int, obj.date))
            self.state.seq = int(cast(int, obj.seq))
            updates_list = cast(list[Any], obj.updates)
            users = cast(list[Any], getattr(obj, "users", []))
            chats = cast(list[Any], getattr(obj, "chats", []))

            # Best-effort pts tracking for updates that carry pts/pts_count.
            for u in updates_list:
                self._apply_pts_from_update(u)

            return AppliedUpdates(
                updates=list(updates_list),
                new_messages=[],
                users=list(users),
                chats=list(chats),
            )

        # Best-effort: single Update that carries pts/pts_count.
        self._apply_pts_from_update(obj)
        return AppliedUpdates(updates=[obj], new_messages=[], users=[], chats=[])

    def _apply_pts_from_update(self, update: Any) -> None:
        if self.state is None:
            return
        pts = getattr(update, "pts", None)
        pts_count = getattr(update, "pts_count", None)
        if isinstance(pts, int) and isinstance(pts_count, int):
            expected = self.state.pts + pts_count
            if pts != expected:
                # Gap will be handled when we see an updatesTooLong or higher-level wrapper.
                logger.debug(
                    "PTS mismatch in update (%s): have=%s expected=%s got=%s",
                    getattr(update, "TL_NAME", type(update).__name__),
                    self.state.pts,
                    expected,
                    pts,
                )
                return
            self.state.pts = pts
            return

    async def _fetch_difference(self) -> AppliedUpdates:
        if self.state is None:
            raise UpdatesEngineError("No state")

        out_updates: list[Any] = []
        out_messages: list[Any] = []
        out_users: list[Any] = []
        out_chats: list[Any] = []

        while True:
            req = UpdatesGetDifference(
                flags=0 if self._pts_total_limit is None else 1,
                pts=self.state.pts,
                pts_limit=None,
                pts_total_limit=self._pts_total_limit,
                date=self.state.date,
                qts=self.state.qts,
                qts_limit=None,
            )
            diff = await self._invoke_api(req)

            if isinstance(diff, UpdatesDifferenceEmpty):
                self.state.date = int(cast(int, diff.date))
                self.state.seq = int(cast(int, diff.seq))
                return AppliedUpdates(
                    updates=out_updates,
                    new_messages=out_messages,
                    users=out_users,
                    chats=out_chats,
                )

            if isinstance(diff, UpdatesDifferenceTooLong):
                # Reset state via getState (simple & safe).
                logger.warning("differenceTooLong received; reinitializing updates state")
                _ = int(cast(int, diff.pts))
                await self.initialize()
                return AppliedUpdates(
                    updates=out_updates,
                    new_messages=out_messages,
                    users=out_users,
                    chats=out_chats,
                )

            if isinstance(diff, UpdatesDifference):
                out_messages.extend(cast(list[Any], diff.new_messages))
                out_updates.extend(cast(list[Any], diff.other_updates))
                out_users.extend(cast(list[Any], diff.users))
                out_chats.extend(cast(list[Any], diff.chats))
                self.state = UpdatesState.from_tl(cast(TlUpdatesState, diff.state))
                return AppliedUpdates(
                    updates=out_updates,
                    new_messages=out_messages,
                    users=out_users,
                    chats=out_chats,
                )

            if isinstance(diff, UpdatesDifferenceSlice):
                out_messages.extend(cast(list[Any], diff.new_messages))
                out_updates.extend(cast(list[Any], diff.other_updates))
                out_users.extend(cast(list[Any], diff.users))
                out_chats.extend(cast(list[Any], diff.chats))
                self.state = UpdatesState.from_tl(cast(TlUpdatesState, diff.intermediate_state))
                continue

            raise UpdatesEngineError(
                f"Unexpected updates.getDifference result: {type(diff).__name__}"
            )

