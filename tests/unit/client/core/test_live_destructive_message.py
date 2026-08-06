from __future__ import annotations

from types import SimpleNamespace

import pytest

from tests.live._destructive_message import (
    DestructiveLiveGateError,
    extract_sent_message_id,
    find_exact_message,
    resolve_destructive_message_gate,
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
