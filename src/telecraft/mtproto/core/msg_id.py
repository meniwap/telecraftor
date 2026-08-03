from __future__ import annotations

import time


class MsgIdGenerator:
    """
    Generate MTProto message ids.

    Properties required by Telegram:
    - strictly increasing per session
    - divisible by 4
    - roughly based on unix time
    """

    __slots__ = ("_last", "_time_offset")

    def __init__(self, *, server_time: int | float | None = None) -> None:
        self._last = 0
        self._time_offset = 0.0
        if server_time is not None:
            self.synchronize(float(server_time), reset_last=True)

    def now(self) -> float:
        """Return the best known server-aligned Unix time."""

        return time.time() + self._time_offset

    def synchronize(self, server_time: int | float, *, reset_last: bool) -> None:
        """Align generated IDs to server time after auth or a bad-msg correction."""

        self._time_offset = float(server_time) - time.time()
        if reset_last:
            # A msg_id rejected for being too high/low must not constrain its
            # corrected replacement. It was never accepted into the session.
            self._last = 0

    def synchronize_from_msg_id(self, server_msg_id: int, *, reset_last: bool = True) -> None:
        self.synchronize(int(server_msg_id) >> 32, reset_last=reset_last)

    def observe(self, remote_msg_id: int) -> None:
        """
        Observe a remote message id and ensure future ids are higher.

        Telegram servers can return msg_id slightly ahead of local clock.
        Many flows (including the auth key exchange) require client msg_id
        to be strictly increasing over the whole session, so we bump our
        internal last value based on the highest observed remote msg_id.
        """

        # Client msg_id must be divisible by 4; servers' msg_id may be 1/2/3 mod 4.
        # Using floor(remote) keeps divisibility, and next() will add +4 if needed.
        remote_floor = int(remote_msg_id) & ~3
        if remote_floor > self._last:
            self._last = remote_floor

    def next(self) -> int:
        now = self.now()
        msg_id = int(now * (2**32))
        msg_id &= ~3  # divisible by 4
        if msg_id <= self._last:
            msg_id = self._last + 4
        # MTProto requires a non-zero fractional (low 32-bit) portion. This
        # matters with coarse/frozen clocks and after integer time sync.
        if msg_id & 0xFFFFFFFF == 0:
            msg_id += 4
        self._last = msg_id
        return msg_id
