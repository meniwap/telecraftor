from __future__ import annotations

import pytest

from telecraft.mtproto.core import msg_id as msg_id_module
from telecraft.mtproto.core.msg_id import MsgIdGenerator


def test_msg_id_monotonic_and_divisible_by_4() -> None:
    gen = MsgIdGenerator()
    ids = [gen.next() for _ in range(100)]
    assert all(x % 4 == 0 for x in ids)
    assert ids == sorted(ids)
    assert len(set(ids)) == len(ids)


def test_msg_id_observe_bumps_past_remote_ids() -> None:
    gen = MsgIdGenerator()
    first = gen.next()
    # Simulate server msg_id being ahead (can be 1/2/3 mod 4)
    gen.observe(first + 1_000_000_001)  # not divisible by 4
    nxt = gen.next()
    assert nxt % 4 == 0
    assert nxt > first + 1_000_000_001


def test_msg_id_generator_uses_server_time_offset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local_time = 1_700_000_000.25
    server_time = 1_700_003_600
    monkeypatch.setattr(msg_id_module.time, "time", lambda: local_time)

    gen = MsgIdGenerator(server_time=server_time)

    assert gen.now() == pytest.approx(float(server_time))
    assert gen.next() >> 32 == server_time


def test_msg_id_resynchronization_can_replace_a_rejected_future_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local_time = 1_700_000_000.0
    monkeypatch.setattr(msg_id_module.time, "time", lambda: local_time)
    gen = MsgIdGenerator(server_time=local_time + 3_600)
    rejected = gen.next()

    server_msg_id = (int(local_time) << 32) | 1
    gen.synchronize_from_msg_id(server_msg_id)
    corrected = gen.next()

    assert corrected < rejected
    assert corrected >> 32 == int(local_time)
    assert corrected % 4 == 0


def test_msg_id_fraction_is_nonzero_with_an_exact_integer_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(msg_id_module.time, "time", lambda: 1_700_000_000.0)

    msg_id = MsgIdGenerator().next()

    assert msg_id & 0xFFFFFFFF != 0
    assert msg_id % 4 == 0
