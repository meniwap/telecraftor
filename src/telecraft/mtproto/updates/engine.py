from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, cast

from telecraft.mtproto.rpc.sender import RpcErrorException
from telecraft.mtproto.updates.state import UpdatesState
from telecraft.tl.generated.functions import (
    UpdatesGetChannelDifference,
    UpdatesGetDifference,
    UpdatesGetState,
)
from telecraft.tl.generated.types import (
    ChannelMessagesFilterEmpty,
    InputChannel,
    UpdateChannelTooLong,
    UpdatePtsChanged,
    Updates,
    UpdatesChannelDifference,
    UpdatesChannelDifferenceEmpty,
    UpdatesChannelDifferenceTooLong,
    UpdatesCombined,
    UpdatesDifference,
    UpdatesDifferenceEmpty,
    UpdatesDifferenceSlice,
    UpdatesDifferenceTooLong,
    UpdateShort,
    UpdateShortChatMessage,
    UpdateShortMessage,
    UpdateShortSentMessage,
    UpdatesTooLong,
)
from telecraft.tl.generated.types import (
    UpdatesState as TlUpdatesState,
)

logger = logging.getLogger(__name__)

_MAX_DIFFERENCE_PAGES = 4096
_MAX_CHANNEL_DIFFERENCE_PAGES = 4096

_CHANNEL_DIFFERENCE_UNAVAILABLE_ERRORS = frozenset(
    {
        "CHANNEL_INVALID",
        "CHANNEL_PRIVATE",
        "CHANNEL_PUBLIC_GROUP_NA",
    }
)


class UpdatesEngineError(Exception):
    pass


@dataclass(slots=True)
class AppliedUpdates:
    updates: list[Any]
    new_messages: list[Any]
    users: list[Any]
    chats: list[Any]

    @classmethod
    def empty(cls) -> AppliedUpdates:
        return cls(updates=[], new_messages=[], users=[], chats=[])

    def extend(self, other: AppliedUpdates) -> None:
        self.updates.extend(other.updates)
        self.new_messages.extend(other.new_messages)
        self.users.extend(other.users)
        self.chats.extend(other.chats)


@dataclass(slots=True, eq=False)
class _UpdatesCheckpoint(UpdatesState):
    """Runtime checkpoint including the non-persisted channel cursors."""

    channel_pts: dict[int, int] = field(default_factory=dict, repr=False)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, UpdatesState):
            return NotImplemented
        return (
            self.pts,
            self.qts,
            self.date,
            self.seq,
        ) == (
            other.pts,
            other.qts,
            other.date,
            other.seq,
        )


@dataclass(slots=True)
class _MessageBoxPreview:
    pts: int
    qts: int
    accepted: list[Any]
    ordinary: list[Any]
    channel: list[Any]
    gap: bool = False


class UpdatesEngine:
    """
    MTProto updates consistency engine:
    - Initializes state with updates.getState
    - Catches a persisted state up with updates.getDifference before live consumption
    - Applies incoming updates only after validating seq, pts and qts continuity
    - Fills gaps using updates.getDifference (handles slice/tooLong)
    - Tracks per-channel pts and recovers updateChannelTooLong/channel gaps independently

    Channel pts are intentionally not represented by ``UpdatesState`` yet. The in-memory
    channel cursor is therefore only an optimization within one process; a restarted
    client always uses ``force=True`` and asks Telegram for an authoritative channel
    difference instead of claiming that the cursor is durable.
    """

    def __init__(
        self,
        *,
        invoke_api: Callable[[Any], Awaitable[Any]],
        resolve_input_channel: Callable[[int], Any] | None = None,
        pts_total_limit: int | None = None,
    ) -> None:
        self._invoke_api = invoke_api
        self._resolve_input_channel = resolve_input_channel
        self._pts_total_limit = pts_total_limit
        self.state: UpdatesState | None = None
        # TODO(channel-pts-persistence): persist this in a separately versioned,
        # private state file before treating channel cursors as durable.
        self._channel_pts: dict[int, int] = {}
        self._initial_catch_up: tuple[UpdatesState, AppliedUpdates] | None = None

    async def initialize(self, *, initial_state: UpdatesState | None = None) -> UpdatesState:
        """
        Initialize updates engine state.

        - If initial_state is provided (e.g. loaded from disk), updates.getDifference is
          called immediately so updates received while the process was offline are not
          delayed until another live update happens to arrive.
        - Otherwise we fetch updates.getState from the server.

        The catch-up batch is retained until ``take_initial_catch_up`` is called by the
        consumer. This keeps the historical updates coupled to the state transition that
        produced them instead of silently discarding them during startup.
        """
        self._initial_catch_up = None
        if initial_state is not None:
            self.state = self._copy_state(initial_state)
            checkpoint = self.checkpoint()
            applied = await self._fetch_difference()
            self._initial_catch_up = (checkpoint, applied)
            return self.state
        res = await self._invoke_api(UpdatesGetState())
        self.state = UpdatesState.from_tl(res)
        return self.state

    def take_initial_catch_up(self) -> tuple[UpdatesState, AppliedUpdates] | None:
        """Return the startup catch-up batch exactly once."""
        pending = self._initial_catch_up
        self._initial_catch_up = None
        return pending

    def checkpoint(self) -> UpdatesState:
        """Take a copy suitable for rolling back an undelivered output batch."""
        if self.state is None:
            raise UpdatesEngineError("No state")
        return _UpdatesCheckpoint(
            pts=int(self.state.pts),
            qts=int(self.state.qts),
            date=int(self.state.date),
            seq=int(self.state.seq),
            channel_pts=dict(self._channel_pts),
        )

    def restore(self, checkpoint: UpdatesState) -> None:
        """Restore a checkpoint after delivery was cancelled or failed."""
        self.state = self._copy_state(checkpoint)
        if isinstance(checkpoint, _UpdatesCheckpoint):
            self._channel_pts = dict(checkpoint.channel_pts)
        else:
            # A persisted/global-only checkpoint cannot prove any channel cursor.
            # Forgetting the optimization is safer than retaining an acknowledged
            # cursor that might belong to a later, undelivered batch.
            self._channel_pts.clear()

    @staticmethod
    def _copy_state(state: UpdatesState) -> UpdatesState:
        return UpdatesState(
            pts=int(state.pts),
            qts=int(state.qts),
            date=int(state.date),
            seq=int(state.seq),
        )

    async def apply(self, obj: Any) -> AppliedUpdates:
        if self.state is None:
            raise UpdatesEngineError("Updates engine not initialized (call initialize())")

        checkpoint = self.checkpoint()
        try:
            return await self._apply(obj)
        except BaseException:
            self.restore(checkpoint)
            raise

    async def recover(self) -> AppliedUpdates:
        """Fetch the global difference transactionally after an out-of-band signal."""
        if self.state is None:
            raise UpdatesEngineError("Updates engine not initialized (call initialize())")

        checkpoint = self.checkpoint()
        try:
            return await self._fetch_difference()
        except BaseException:
            self.restore(checkpoint)
            raise

    async def _refresh_state(self) -> AppliedUpdates:
        """Replace global counters with an authoritative ``updates.getState`` result."""
        res = await self._invoke_api(UpdatesGetState())
        self.state = UpdatesState.from_tl(res)
        return AppliedUpdates.empty()

    async def _apply(self, obj: Any) -> AppliedUpdates:
        if self.state is None:
            raise UpdatesEngineError("No state")

        # updatesTooLong: must fetch difference.
        if isinstance(obj, UpdatesTooLong):
            return await self._fetch_difference()

        # updatePtsChanged invalidates the local common PTS. It carries no
        # event payload; Telegram instructs clients to fetch authoritative state.
        if isinstance(obj, UpdatePtsChanged):
            return await self._refresh_state()

        if isinstance(obj, UpdateChannelTooLong):
            channel_id = self._channel_id_from_update(obj)
            if channel_id is None:
                raise UpdatesEngineError("updateChannelTooLong has no channel_id")
            trigger_pts = getattr(obj, "pts", None)
            return await self._fetch_channel_difference(
                channel_id,
                initial_pts=trigger_pts if isinstance(trigger_pts, int) else None,
            )

        # Short variants do not participate in seq, but their message-box counters
        # still need the same gap and duplicate handling as nested updates.
        if isinstance(obj, (UpdateShortMessage, UpdateShortChatMessage, UpdateShortSentMessage)):
            return await self._apply_unsequenced([obj], date=int(cast(int, obj.date)))

        if isinstance(obj, UpdateShort):
            if isinstance(obj.update, UpdatePtsChanged):
                return await self._refresh_state()
            return await self._apply_unsequenced(
                [obj.update],
                date=int(cast(int, obj.date)),
            )

        if isinstance(obj, (Updates, UpdatesCombined)):
            envelope_updates = cast(list[Any], obj.updates)
            if any(isinstance(update, UpdatePtsChanged) for update in envelope_updates):
                return await self._apply_pts_changed_envelope(obj)
            return await self._apply_envelope(obj)

        return await self._apply_unsequenced([obj], date=None)

    async def _apply_pts_changed_envelope(
        self,
        obj: Updates | UpdatesCombined,
    ) -> AppliedUpdates:
        """Refresh global state without dropping co-delivered independent updates."""

        updates = [
            update
            for update in cast(list[Any], obj.updates)
            if not isinstance(update, UpdatePtsChanged)
        ]
        users = cast(list[Any], getattr(obj, "users", []))
        chats = cast(list[Any], getattr(obj, "chats", []))

        # Classify siblings against the last committed counters.  Classifying
        # after getState would make a co-delivered update whose pts/qts is
        # reflected by that snapshot look stale, dropping its payload.
        preview = self._preview_message_boxes(updates)

        if preview.gap:
            # Recover from the last committed counters before replacing them
            # with getState.  Refreshing first would skip the very range that
            # contains the co-delivered payload.  Difference owns all countered
            # output in this branch, so do not append preview.accepted again.
            applied = await self._fetch_difference()
            await self._refresh_state()
            applied.updates.extend(preview.ordinary)
        else:
            await self._refresh_state()
            # getState remains authoritative for every global counter.  The
            # preview is used only to decide which payloads were new at receipt
            # time, so each accepted sibling is still delivered exactly once.
            applied = AppliedUpdates(
                updates=[*preview.accepted, *preview.ordinary],
                new_messages=[],
                users=[],
                chats=[],
            )

        applied.extend(await self._apply_channel_updates(preview.channel, chats=chats))
        if applied.updates or applied.new_messages:
            applied.users.extend(users)
            applied.chats.extend(chats)
        return applied

    async def _apply_unsequenced(
        self,
        updates: list[Any],
        *,
        date: int | None,
    ) -> AppliedUpdates:
        if self.state is None:
            raise UpdatesEngineError("No state")
        preview = self._preview_message_boxes(updates)

        if preview.gap:
            applied = await self._fetch_difference()
        else:
            self.state.pts = preview.pts
            self.state.qts = preview.qts
            applied = AppliedUpdates(
                updates=[*preview.accepted, *preview.ordinary],
                new_messages=[],
                users=[],
                chats=[],
            )
            if date is not None and applied.updates:
                self.state.date = int(date)

        channel_applied = await self._apply_channel_updates(preview.channel)
        applied.extend(channel_applied)
        return applied

    async def _apply_envelope(self, obj: Updates | UpdatesCombined) -> AppliedUpdates:
        if self.state is None:
            raise UpdatesEngineError("No state")
        updates = cast(list[Any], obj.updates)
        users = cast(list[Any], getattr(obj, "users", []))
        chats = cast(list[Any], getattr(obj, "chats", []))
        preview = self._preview_message_boxes(updates)
        seq_status = self._seq_status(obj)

        # A global pts/qts or seq gap is recovered from the old, fully committed
        # state. Channel message boxes remain independent and are handled below.
        if preview.gap or seq_status == "gap":
            if preview.gap:
                logger.info("PTS/QTS gap detected; fetching difference")
            else:
                logger.info(
                    "SEQ gap detected (have=%s, seq_start=%s, seq=%s); fetching difference",
                    self.state.seq,
                    getattr(obj, "seq_start", getattr(obj, "seq", None)),
                    getattr(obj, "seq", None),
                )
            applied = await self._fetch_difference()
        else:
            self.state.pts = preview.pts
            self.state.qts = preview.qts
            applied = AppliedUpdates(
                updates=list(preview.accepted),
                new_messages=[],
                users=[],
                chats=[],
            )
            if seq_status == "ready":
                applied.updates.extend(preview.ordinary)
                self.state.date = int(cast(int, obj.date))
                seq = int(cast(int, obj.seq))
                if seq != 0:
                    self.state.seq = seq
            else:
                logger.debug(
                    "Dropping stale seq-only updates (have seq=%s, got seq=%s)",
                    self.state.seq,
                    getattr(obj, "seq", None),
                )

        channel_applied = await self._apply_channel_updates(preview.channel, chats=chats)
        applied.extend(channel_applied)
        if applied.updates or applied.new_messages:
            applied.users.extend(users)
            applied.chats.extend(chats)
        return applied

    def _seq_status(self, obj: Updates | UpdatesCombined) -> str:
        """Return ``ready``, ``stale`` or ``gap`` for a sequenced envelope."""
        if self.state is None:
            raise UpdatesEngineError("No state")
        seq = int(cast(int, obj.seq))
        seq_start = int(cast(int, getattr(obj, "seq_start", seq)))
        if seq < 0 or seq_start < 0:
            return "gap"

        # seq_start=0 is Telegram's explicit unordered special case. The payload
        # is applied immediately even if its final seq value is non-zero.
        if seq_start == 0:
            return "ready"
        if seq < seq_start:
            return "gap"
        expected = self.state.seq + 1
        if expected == seq_start:
            return "ready"
        if expected > seq_start:
            return "stale"
        return "gap"

    def _preview_message_boxes(self, updates: list[Any]) -> _MessageBoxPreview:
        """Classify and validate independent global, qts and channel sequences."""
        if self.state is None:
            raise UpdatesEngineError("No state")
        pts = int(self.state.pts)
        qts = int(self.state.qts)
        accepted: list[Any] = []
        ordinary: list[Any] = []
        channel: list[Any] = []
        gap = False

        for update in updates:
            if isinstance(update, UpdateChannelTooLong) or self._looks_like_channel_counter(update):
                channel.append(update)
                continue

            update_qts = getattr(update, "qts", None)
            if isinstance(update_qts, int):
                expected_qts = qts + 1
                if update_qts < 0 or expected_qts < update_qts:
                    gap = True
                elif expected_qts == update_qts:
                    qts = int(update_qts)
                    accepted.append(update)
                # expected_qts > update_qts is a duplicate and is ignored.
                continue

            update_pts = getattr(update, "pts", None)
            pts_count = getattr(update, "pts_count", None)
            tl_name = str(getattr(update, "TL_NAME", type(update).__name__))
            if isinstance(update_pts, int):
                count = 0 if pts_count is None else pts_count
                if update_pts < 0 or not isinstance(count, int) or count < 0:
                    logger.info(
                        "Invalid pts/pts_count in %s (%s/%s); fetching difference",
                        tl_name,
                        update_pts,
                        count,
                    )
                    gap = True
                    continue
                expected_pts = pts + count
                if expected_pts < update_pts:
                    logger.info(
                        "PTS gap in %s (have=%s, expected=%s, got=%s); fetching difference",
                        tl_name,
                        pts,
                        expected_pts,
                        update_pts,
                    )
                    gap = True
                elif expected_pts == update_pts:
                    pts = int(update_pts)
                    accepted.append(update)
                # expected_pts > update_pts is a duplicate and is ignored.
                continue

            ordinary.append(update)

        return _MessageBoxPreview(
            pts=pts,
            qts=qts,
            accepted=accepted,
            ordinary=ordinary,
            channel=channel,
            gap=gap,
        )

    @staticmethod
    def _channel_id_from_update(update: Any) -> int | None:
        channel_id = getattr(update, "channel_id", None)
        if isinstance(channel_id, int):
            return int(channel_id)

        for container_name in ("message", "peer"):
            container = getattr(update, container_name, None)
            peer = getattr(container, "peer_id", container)
            if str(getattr(peer, "TL_NAME", "")) != "peerChannel":
                continue
            nested_channel_id = getattr(peer, "channel_id", None)
            if isinstance(nested_channel_id, int):
                return int(nested_channel_id)
        return None

    @classmethod
    def _looks_like_channel_counter(cls, update: Any) -> bool:
        if not isinstance(getattr(update, "pts", None), int):
            return False
        tl_name = str(getattr(update, "TL_NAME", type(update).__name__)).lower()
        return "channel" in tl_name or cls._channel_id_from_update(update) is not None

    @staticmethod
    def _input_channel_from_chats(channel_id: int, chats: list[Any]) -> InputChannel | None:
        for chat in chats:
            # `min` access hashes are context-bound and cannot be used for
            # updates.getChannelDifference.
            if bool(getattr(chat, "min", False)):
                continue
            chat_id = getattr(chat, "id", None)
            access_hash = getattr(chat, "access_hash", None)
            if isinstance(chat_id, int) and chat_id == channel_id and isinstance(access_hash, int):
                return InputChannel(channel_id=channel_id, access_hash=access_hash)
        return None

    async def _apply_channel_updates(
        self,
        updates: list[Any],
        *,
        chats: list[Any] | None = None,
    ) -> AppliedUpdates:
        applied = AppliedUpdates.empty()
        supporting_chats = chats or []
        for update in updates:
            channel_id = self._channel_id_from_update(update)
            if channel_id is None:
                raise UpdatesEngineError(
                    f"Cannot determine channel_id for "
                    f"{getattr(update, 'TL_NAME', type(update).__name__)}"
                )
            input_channel = self._input_channel_from_chats(channel_id, supporting_chats)

            if isinstance(update, UpdateChannelTooLong):
                trigger_pts = getattr(update, "pts", None)
                applied.extend(
                    await self._fetch_channel_difference(
                        channel_id,
                        input_channel=input_channel,
                        initial_pts=(trigger_pts if isinstance(trigger_pts, int) else None),
                    )
                )
                continue

            remote_pts = getattr(update, "pts", None)
            if not isinstance(remote_pts, int):
                raise UpdatesEngineError("Channel update has no integer pts")
            count_value = getattr(update, "pts_count", None)
            pts_count = 0 if count_value is None else count_value
            local_pts = self._channel_pts.get(channel_id)
            if local_pts is None or not isinstance(pts_count, int) or pts_count < 0:
                applied.extend(
                    await self._fetch_channel_difference(
                        channel_id,
                        input_channel=input_channel,
                    )
                )
                continue

            expected_pts = local_pts + pts_count
            if expected_pts > remote_pts:
                logger.debug(
                    "Dropping duplicate channel update channel_id=%s have=%s got=%s count=%s",
                    channel_id,
                    local_pts,
                    remote_pts,
                    pts_count,
                )
                continue
            if expected_pts < remote_pts:
                logger.info(
                    "Channel PTS gap channel_id=%s have=%s got=%s count=%s; fetching difference",
                    channel_id,
                    local_pts,
                    remote_pts,
                    pts_count,
                )
                applied.extend(
                    await self._fetch_channel_difference(
                        channel_id,
                        input_channel=input_channel,
                    )
                )
                continue

            self._channel_pts[channel_id] = int(remote_pts)
            applied.updates.append(update)
        return applied

    async def _expand_difference_channel_updates(
        self,
        applied: AppliedUpdates,
    ) -> AppliedUpdates:
        channel_updates: list[Any] = []
        ordinary_updates: list[Any] = []
        for update in applied.updates:
            if isinstance(update, UpdateChannelTooLong) or self._looks_like_channel_counter(update):
                channel_updates.append(update)
            else:
                ordinary_updates.append(update)
        if not channel_updates:
            return applied

        expanded = AppliedUpdates(
            updates=ordinary_updates,
            new_messages=list(applied.new_messages),
            users=list(applied.users),
            chats=list(applied.chats),
        )
        expanded.extend(await self._apply_channel_updates(channel_updates, chats=applied.chats))
        return expanded

    async def _fetch_difference(self) -> AppliedUpdates:
        if self.state is None:
            raise UpdatesEngineError("No state")

        out_updates: list[Any] = []
        out_messages: list[Any] = []
        out_users: list[Any] = []
        out_chats: list[Any] = []
        refresh_state_after_difference = False

        for _page in range(_MAX_DIFFERENCE_PAGES):
            previous_state = self._copy_state(self.state)
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
                if refresh_state_after_difference:
                    await self._refresh_state()
                return await self._expand_difference_channel_updates(
                    AppliedUpdates(
                        updates=out_updates,
                        new_messages=out_messages,
                        users=out_users,
                        chats=out_chats,
                    )
                )

            if isinstance(diff, UpdatesDifferenceTooLong):
                # Only the common message box is too old to recover through
                # the old PTS. Keep qts/date/seq intact because they are
                # independent sequences, then refetch using the supplied PTS as
                # required by Telegram instead of silently skipping those boxes.
                logger.warning("differenceTooLong received; retrying from the supplied common pts")
                next_pts = int(cast(int, diff.pts))
                if next_pts == self.state.pts:
                    raise UpdatesEngineError(
                        "updates.differenceTooLong made no common pts progress"
                    )
                self.state.pts = next_pts
                continue

            if isinstance(diff, UpdatesDifference):
                out_messages.extend(cast(list[Any], diff.new_messages))
                other_updates = cast(list[Any], diff.other_updates)
                refresh_state_after_difference = refresh_state_after_difference or any(
                    isinstance(update, UpdatePtsChanged) for update in other_updates
                )
                out_updates.extend(
                    update for update in other_updates if not isinstance(update, UpdatePtsChanged)
                )
                out_users.extend(cast(list[Any], diff.users))
                out_chats.extend(cast(list[Any], diff.chats))
                self.state = UpdatesState.from_tl(cast(TlUpdatesState, diff.state))
                if refresh_state_after_difference:
                    await self._refresh_state()
                return await self._expand_difference_channel_updates(
                    AppliedUpdates(
                        updates=out_updates,
                        new_messages=out_messages,
                        users=out_users,
                        chats=out_chats,
                    )
                )

            if isinstance(diff, UpdatesDifferenceSlice):
                out_messages.extend(cast(list[Any], diff.new_messages))
                other_updates = cast(list[Any], diff.other_updates)
                refresh_state_after_difference = refresh_state_after_difference or any(
                    isinstance(update, UpdatePtsChanged) for update in other_updates
                )
                out_updates.extend(
                    update for update in other_updates if not isinstance(update, UpdatePtsChanged)
                )
                out_users.extend(cast(list[Any], diff.users))
                out_chats.extend(cast(list[Any], diff.chats))
                self.state = UpdatesState.from_tl(cast(TlUpdatesState, diff.intermediate_state))
                if self.state == previous_state:
                    raise UpdatesEngineError("updates.getDifference slice made no state progress")
                continue

            raise UpdatesEngineError(
                f"Unexpected updates.getDifference result: {type(diff).__name__}"
            )

        raise UpdatesEngineError("Too many updates.getDifference pages")

    async def _fetch_channel_difference(
        self,
        channel_id: int,
        *,
        input_channel: Any | None = None,
        initial_pts: int | None = None,
    ) -> AppliedUpdates:
        """Fetch a channel difference transactionally and paginate until ``final``."""
        if input_channel is None:
            if self._resolve_input_channel is None:
                logger.warning(
                    "Skipping channel difference without an InputChannel resolver channel_id=%s",
                    channel_id,
                )
                self._channel_pts.pop(int(channel_id), None)
                return AppliedUpdates.empty()
            try:
                input_channel = self._resolve_input_channel(int(channel_id))
            except Exception as ex:  # noqa: BLE001
                raise UpdatesEngineError(
                    f"Failed to resolve InputChannel channel_id={channel_id}"
                ) from ex
            if input_channel is None:
                logger.warning(
                    "Skipping channel difference without a reusable full access hash channel_id=%s",
                    channel_id,
                )
                self._channel_pts.pop(int(channel_id), None)
                return AppliedUpdates.empty()

        stored_pts = self._channel_pts.get(int(channel_id))
        if stored_pts is not None:
            pts = int(stored_pts)
            force = False
        else:
            pts = int(initial_pts) if isinstance(initial_pts, int) and initial_pts >= 0 else 1
            force = True

        out_updates: list[Any] = []
        out_messages: list[Any] = []
        out_users: list[Any] = []
        out_chats: list[Any] = []

        for _page in range(_MAX_CHANNEL_DIFFERENCE_PAGES):
            request_pts = int(pts)
            request_force = force
            logger.info(
                "getChannelDifference(channel_id=%s, pts=%s, force=%s)",
                channel_id,
                pts,
                force,
            )
            try:
                diff = await self._invoke_api(
                    UpdatesGetChannelDifference(
                        flags=0,
                        force=force,
                        channel=input_channel,
                        filter=ChannelMessagesFilterEmpty(),
                        pts=int(pts),
                        limit=100,
                    )
                )
            except RpcErrorException as exc:
                if str(exc.message).upper() not in _CHANNEL_DIFFERENCE_UNAVAILABLE_ERRORS:
                    raise
                # A user may leave, lose access to, or receive a min constructor
                # for a channel while global updates continue.  Isolate that
                # channel instead of terminating every update consumer.
                logger.warning(
                    "Channel difference unavailable; isolating channel_id=%s error=%s",
                    channel_id,
                    exc.message,
                )
                self._channel_pts.pop(int(channel_id), None)
                return AppliedUpdates.empty()

            if isinstance(diff, UpdatesChannelDifferenceEmpty):
                logger.info(
                    "channelDifferenceEmpty(channel_id=%s, pts=%s, final=%s)",
                    channel_id,
                    getattr(diff, "pts", None),
                    getattr(diff, "final", None),
                )
                pts = int(cast(int, diff.pts))
                if bool(getattr(diff, "final", False)):
                    self._channel_pts[int(channel_id)] = int(pts)
                    return AppliedUpdates(
                        updates=out_updates,
                        new_messages=out_messages,
                        users=out_users,
                        chats=out_chats,
                    )
                force = False
                if pts == request_pts and force == request_force:
                    raise UpdatesEngineError(
                        "updates.getChannelDifference made no state progress "
                        f"channel_id={channel_id}"
                    )
                continue

            if isinstance(diff, UpdatesChannelDifference):
                logger.info(
                    "channelDifference(channel_id=%s, pts=%s, final=%s, msgs=%s, upd=%s)",
                    channel_id,
                    getattr(diff, "pts", None),
                    getattr(diff, "final", None),
                    len(cast(list[Any], diff.new_messages)),
                    len(cast(list[Any], diff.other_updates)),
                )
                pts = int(cast(int, diff.pts))
                out_messages.extend(cast(list[Any], diff.new_messages))
                out_updates.extend(cast(list[Any], diff.other_updates))
                out_chats.extend(cast(list[Any], diff.chats))
                out_users.extend(cast(list[Any], diff.users))
                if bool(getattr(diff, "final", False)):
                    self._channel_pts[int(channel_id)] = int(pts)
                    return AppliedUpdates(
                        updates=out_updates,
                        new_messages=out_messages,
                        users=out_users,
                        chats=out_chats,
                    )
                force = False
                if pts == request_pts and force == request_force:
                    raise UpdatesEngineError(
                        "updates.getChannelDifference made no state progress "
                        f"channel_id={channel_id}"
                    )
                continue

            if isinstance(diff, UpdatesChannelDifferenceTooLong):
                logger.info(
                    "channelDifferenceTooLong(channel_id=%s, final=%s, msgs=%s)",
                    channel_id,
                    getattr(diff, "final", None),
                    len(cast(list[Any], diff.messages)),
                )
                dlg = getattr(diff, "dialog", None)
                dlg_pts = getattr(dlg, "pts", None)
                if not isinstance(dlg_pts, int):
                    raise UpdatesEngineError(
                        f"channelDifferenceTooLong has no dialog pts channel_id={channel_id}"
                    )
                pts = int(dlg_pts)
                out_messages.extend(cast(list[Any], diff.messages))
                out_chats.extend(cast(list[Any], diff.chats))
                out_users.extend(cast(list[Any], diff.users))
                if bool(getattr(diff, "final", False)):
                    self._channel_pts[int(channel_id)] = int(pts)
                    return AppliedUpdates(
                        updates=out_updates,
                        new_messages=out_messages,
                        users=out_users,
                        chats=out_chats,
                    )
                force = False
                if pts == request_pts and force == request_force:
                    raise UpdatesEngineError(
                        "updates.getChannelDifference made no state progress "
                        f"channel_id={channel_id}"
                    )
                continue

            raise UpdatesEngineError(
                f"Unexpected updates.getChannelDifference result: {type(diff).__name__}"
            )

        raise UpdatesEngineError(
            f"Too many updates.getChannelDifference pages channel_id={channel_id}"
        )
