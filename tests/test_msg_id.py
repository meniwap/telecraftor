from __future__ import annotations

from telecraft.mtproto.core.msg_id import MsgIdGenerator


def test_msg_id_monotonic_and_divisible_by_4() -> None:
    gen = MsgIdGenerator()
    ids = [gen.next() for _ in range(100)]
    assert all(x % 4 == 0 for x in ids)
    assert ids == sorted(ids)
    assert len(set(ids)) == len(ids)


