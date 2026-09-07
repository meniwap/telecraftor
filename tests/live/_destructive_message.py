from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import Any

DESTRUCTIVE_MESSAGE_PROFILE = "destructive_message"

_MESSAGE_WRAPPER_UPDATES = frozenset(
    {
        "updateNewMessage",
        "updateNewChannelMessage",
        "updateEditMessage",
        "updateEditChannelMessage",
    }
)
_DIRECT_MESSAGE_UPDATES = frozenset(
    {
        "message",
        "updateShortMessage",
        "updateShortChatMessage",
    }
)


class DestructiveLiveGateError(ValueError):
    """Raised when any destructive-live authorization gate is missing or inconsistent."""


class MessageUpdateNotObserved(AssertionError):
    """Raised without embedding message content when a bounded update wait expires."""


@dataclass(frozen=True, slots=True)
class ObservedMessageUpdate:
    message_id: int
    update_kind: str
    inspected_updates: int


def normalize_peer(value: object) -> str:
    peer = str(value or "").strip().lower()
    if peer.startswith("@"):
        peer = peer[1:]
    return peer


def resolve_destructive_message_gate(
    *,
    live_profile: str,
    allow_flag: bool,
    env_allow: str | None,
    cli_peer: str | None,
    env_peer: str | None,
    audit_peer: str,
) -> str:
    """Require independent profile, CLI, environment, peer, and audit gates."""

    if live_profile != DESTRUCTIVE_MESSAGE_PROFILE:
        raise DestructiveLiveGateError(
            "Destructive message tests require --live-profile destructive_message"
        )
    if not allow_flag:
        raise DestructiveLiveGateError("Destructive message tests require --allow-destructive-live")
    if (env_allow or "").strip() != "1":
        raise DestructiveLiveGateError(
            "Destructive message tests require TELECRAFT_ALLOW_DESTRUCTIVE_LIVE=1"
        )
    if (audit_peer or "auto").strip().lower() != "auto":
        raise DestructiveLiveGateError(
            "Destructive message tests require --live-audit-peer auto so the test-created "
            "message is the only write"
        )

    normalized_cli_peer = normalize_peer(cli_peer)
    normalized_env_peer = normalize_peer(env_peer)
    if not normalized_cli_peer or not normalized_env_peer:
        raise DestructiveLiveGateError(
            "Destructive message tests require both --live-destructive-peer and "
            "TELECRAFT_DESTRUCTIVE_PEER"
        )
    if normalized_cli_peer != normalized_env_peer:
        raise DestructiveLiveGateError(
            "--live-destructive-peer and TELECRAFT_DESTRUCTIVE_PEER must match"
        )
    return normalized_cli_peer


def _positive_message_id(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


def normalize_message_text(value: object) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, (bytes, bytearray)):
        try:
            return bytes(value).decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            return None
    return None


def message_id_and_text(message: object) -> tuple[int, str] | None:
    message_id = _positive_message_id(getattr(message, "id", None))
    text = normalize_message_text(getattr(message, "message", None))
    if message_id is None or text is None:
        return None
    return message_id, text


def match_exact_message_update(
    update: object,
    *,
    expected_text: str,
    expected_id: int | None,
) -> tuple[int, str] | None:
    """Match only known message-bearing update shapes without rendering their payload."""

    update_kind = str(getattr(update, "TL_NAME", ""))
    if update_kind in _MESSAGE_WRAPPER_UPDATES:
        candidate = getattr(update, "message", None)
    elif update_kind in _DIRECT_MESSAGE_UPDATES:
        candidate = update
    elif update_kind == "updateShortSentMessage":
        # This short result intentionally carries no message text. It is safe to
        # accept only after the send response supplied the exact positive ID.
        if expected_id is None:
            return None
        message_id = _positive_message_id(getattr(update, "id", None))
        if message_id != expected_id:
            return None
        return message_id, update_kind
    else:
        return None

    identity = message_id_and_text(candidate)
    if identity is None:
        return None
    message_id, text = identity
    if text != expected_text or (expected_id is not None and message_id != expected_id):
        return None
    return message_id, update_kind


async def wait_for_exact_message_update(
    recv_update: Callable[[], Awaitable[Any]],
    *,
    expected_text: str,
    expected_id: int | None,
    timeout: float,
    max_updates: int = 512,
) -> ObservedMessageUpdate:
    """Consume updates until the exact test message is found, under one hard deadline."""

    if timeout <= 0:
        raise ValueError("timeout must be positive")
    if max_updates <= 0:
        raise ValueError("max_updates must be positive")

    loop = asyncio.get_running_loop()
    deadline = loop.time() + float(timeout)
    for inspected in range(1, max_updates + 1):
        remaining = deadline - loop.time()
        if remaining <= 0:
            break
        try:
            update = await asyncio.wait_for(recv_update(), timeout=remaining)
        except asyncio.TimeoutError as exc:
            raise MessageUpdateNotObserved(
                f"Exact test-message update was not observed within {float(timeout):.1f}s"
            ) from exc
        match = match_exact_message_update(
            update,
            expected_text=expected_text,
            expected_id=expected_id,
        )
        if match is not None:
            message_id, update_kind = match
            return ObservedMessageUpdate(
                message_id=message_id,
                update_kind=update_kind,
                inspected_updates=inspected,
            )

    raise MessageUpdateNotObserved(
        f"Exact test-message update was not observed after inspecting {max_updates} updates"
    )


def find_exact_message(
    messages: Iterable[object],
    *,
    expected_text: str,
    expected_id: int | None = None,
) -> object | None:
    """Return only a message whose exact text and optional exact ID match."""

    for message in messages:
        identity = message_id_and_text(message)
        if identity is None:
            continue
        message_id, text = identity
        if text == expected_text and (expected_id is None or message_id == expected_id):
            return message
    return None


def extract_sent_message_id(result: Any, *, expected_text: str) -> int | None:
    """Extract an ID only from known send-result shapes, never from arbitrary nested IDs."""

    tl_name = getattr(result, "TL_NAME", "")
    if tl_name == "updateShortSentMessage":
        return _positive_message_id(getattr(result, "id", None))
    if tl_name in {"updateShortMessage", "updateShortChatMessage"}:
        if normalize_message_text(getattr(result, "message", None)) == expected_text:
            return _positive_message_id(getattr(result, "id", None))
        return None
    if tl_name == "updateShort":
        return extract_sent_message_id(
            getattr(result, "update", None),
            expected_text=expected_text,
        )

    updates = getattr(result, "updates", None)
    if not isinstance(updates, Iterable) or isinstance(updates, (str, bytes)):
        return None

    candidates: set[int] = set()
    for update in updates:
        if getattr(update, "TL_NAME", "") not in {
            "updateNewMessage",
            "updateNewChannelMessage",
        }:
            continue
        identity = message_id_and_text(getattr(update, "message", None))
        if identity is not None and identity[1] == expected_text:
            candidates.add(identity[0])
    if len(candidates) == 1:
        return next(iter(candidates))
    return None
