from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from telecraft.client.mtproto import MtprotoClientError
from tests.live._destructive_message import (
    DestructiveLiveGateError,
    MessageUpdateNotObserved,
    extract_sent_message_id,
    find_exact_message,
    match_exact_message_update,
    resolve_destructive_message_gate,
    wait_for_exact_message_update,
)
from tests.live.test_live_destructive_message_roundtrip import (
    _observe_exact_message_update,
)


def _valid_gate(**overrides: object) -> str:
    values: dict[str, object] = {
        "live_profile": "destructive_message",
        "allow_flag": True,
        "env_allow": "1",
        "cli_peer": "@ApprovedPeer",
        "env_peer": "approvedpeer",
        "audit_peer": "auto",
    }
    values.update(overrides)
    return resolve_destructive_message_gate(**values)  # type: ignore[arg-type]


def test_destructive_gate__requires_every_independent_gate() -> None:
    assert _valid_gate() == "approvedpeer"

    invalid_cases = (
        ({"live_profile": "prod_safe"}, "--live-profile destructive_message"),
        ({"allow_flag": False}, "--allow-destructive-live"),
        ({"env_allow": "true"}, "TELECRAFT_ALLOW_DESTRUCTIVE_LIVE=1"),
        ({"cli_peer": ""}, "both --live-destructive-peer"),
        ({"env_peer": "someone-else"}, "must match"),
        ({"audit_peer": "approvedpeer"}, "--live-audit-peer auto"),
    )
    for overrides, expected_error in invalid_cases:
        with pytest.raises(DestructiveLiveGateError, match=expected_error):
            _valid_gate(**overrides)


def test_extract_sent_message_id__accepts_only_known_safe_shapes() -> None:
    text = "unique text"
    assert (
        extract_sent_message_id(
            SimpleNamespace(TL_NAME="updateShortSentMessage", id=42),
            expected_text=text,
        )
        == 42
    )

    message = SimpleNamespace(id=43, message=text)
    result = SimpleNamespace(
        TL_NAME="updates",
        updates=[SimpleNamespace(TL_NAME="updateNewMessage", message=message)],
    )
    assert extract_sent_message_id(result, expected_text=text) == 43

    assert (
        extract_sent_message_id(
            SimpleNamespace(TL_NAME="unrelated", id=999),
            expected_text=text,
        )
        is None
    )
    ambiguous = SimpleNamespace(
        TL_NAME="updates",
        updates=[
            SimpleNamespace(
                TL_NAME="updateNewMessage",
                message=SimpleNamespace(id=1, message=text),
            ),
            SimpleNamespace(
                TL_NAME="updateNewMessage",
                message=SimpleNamespace(id=2, message=text),
            ),
        ],
    )
    assert extract_sent_message_id(ambiguous, expected_text=text) is None


def test_message_matching__normalizes_utf8_bytes_strictly() -> None:
    text = "בדיקת telecraft"
    encoded = text.encode()
    short = SimpleNamespace(TL_NAME="updateShortMessage", id=51, message=encoded)

    assert extract_sent_message_id(short, expected_text=text) == 51
    assert (
        find_exact_message(
            [SimpleNamespace(id=51, message=bytearray(encoded))],
            expected_text=text,
            expected_id=51,
        )
        is not None
    )
    assert (
        find_exact_message(
            [SimpleNamespace(id=51, message=b"\xff")],
            expected_text=text,
        )
        is None
    )


def test_find_exact_message__requires_exact_text_and_optional_id() -> None:
    messages = [
        SimpleNamespace(id=10, message="token initial"),
        SimpleNamespace(id=11, message="token edited"),
    ]

    assert find_exact_message(messages, expected_text="token edited") is messages[1]
    assert find_exact_message(messages, expected_text="token edited", expected_id=10) is None


def test_match_exact_message_update__accepts_only_exact_known_shapes() -> None:
    text = "private unique live text"
    message = SimpleNamespace(id=71, message=text)

    assert match_exact_message_update(
        SimpleNamespace(TL_NAME="updateNewMessage", message=message),
        expected_text=text,
        expected_id=71,
    ) == (71, "updateNewMessage")
    assert match_exact_message_update(
        SimpleNamespace(TL_NAME="message", id=71, message=text.encode()),
        expected_text=text,
        expected_id=71,
    ) == (71, "message")
    assert match_exact_message_update(
        SimpleNamespace(TL_NAME="updateShortSentMessage", id=71),
        expected_text=text,
        expected_id=71,
    ) == (71, "updateShortSentMessage")

    assert (
        match_exact_message_update(
            SimpleNamespace(TL_NAME="updateNewMessage", message=message),
            expected_text="different text",
            expected_id=71,
        )
        is None
    )
    assert (
        match_exact_message_update(
            SimpleNamespace(TL_NAME="updateShortSentMessage", id=71),
            expected_text=text,
            expected_id=None,
        )
        is None
    )
    assert (
        match_exact_message_update(
            SimpleNamespace(TL_NAME="unrelated", message=message),
            expected_text=text,
            expected_id=71,
        )
        is None
    )


def test_wait_for_exact_message_update__skips_unrelated_without_rendering_payload() -> None:
    async def run() -> None:
        text = "do not render this message"
        updates = iter(
            [
                SimpleNamespace(TL_NAME="updateUser", user_id=1),
                SimpleNamespace(
                    TL_NAME="updateNewMessage",
                    message=SimpleNamespace(id=82, message=text),
                ),
            ]
        )

        async def recv() -> object:
            return next(updates)

        observed = await wait_for_exact_message_update(
            recv,
            expected_text=text,
            expected_id=82,
            timeout=1.0,
        )
        assert observed.message_id == 82
        assert observed.update_kind == "updateNewMessage"
        assert observed.inspected_updates == 2

    asyncio.run(run())


def test_wait_for_exact_message_update__has_bounded_redacted_failure() -> None:
    async def run() -> None:
        secret_text = "must not appear in the assertion"

        async def recv() -> object:
            return SimpleNamespace(TL_NAME="updateUser", user_id=1)

        with pytest.raises(MessageUpdateNotObserved) as caught:
            await wait_for_exact_message_update(
                recv,
                expected_text=secret_text,
                expected_id=91,
                timeout=1.0,
                max_updates=2,
            )
        assert secret_text not in str(caught.value)
        assert "2 updates" in str(caught.value)

    asyncio.run(run())


def test_observe_exact_message_update__uses_one_stop_start_catch_up() -> None:
    async def run() -> None:
        expected_text = "private catch-up payload"

        class FakeUpdates:
            def __init__(self) -> None:
                self.phase = "initial"
                self.stopped = asyncio.Event()
                self.stop_calls = 0
                self.start_calls = 0

            async def recv(self) -> object:
                if self.phase == "initial":
                    await self.stopped.wait()
                    raise MtprotoClientError("Updates stopped")
                return SimpleNamespace(TL_NAME="message", id=101, message=expected_text)

            async def stop(self) -> None:
                self.stop_calls += 1
                self.phase = "stopped"
                self.stopped.set()

            async def start(self, *, timeout: float) -> None:
                assert timeout > 0
                self.start_calls += 1
                self.phase = "restarted"

        updates = FakeUpdates()
        client = SimpleNamespace(updates=updates)
        observed = await _observe_exact_message_update(
            client=client,
            expected_text=expected_text,
            expected_id=101,
            timeout=1.0,
        )

        assert observed.message_id == 101
        assert observed.update_kind == "message"
        assert updates.stop_calls == 1
        assert updates.start_calls == 1

    asyncio.run(run())
