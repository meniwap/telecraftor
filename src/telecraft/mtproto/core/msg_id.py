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

    __slots__ = ("_last",)

    def __init__(self) -> None:
        self._last = 0

    def next(self) -> int:
        now = time.time()
        msg_id = int(now * (2**32))
        msg_id &= ~3  # divisible by 4
        if msg_id <= self._last:
            msg_id = self._last + 4
        self._last = msg_id
        return msg_id


