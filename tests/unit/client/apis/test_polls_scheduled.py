"""Tests for polls, quizzes, and scheduled messages."""

from __future__ import annotations

import asyncio
from typing import Any

from telecraft.client.mtproto import ClientInit, MtprotoClient


def _make_connected_client() -> MtprotoClient:
    c = MtprotoClient(network="test", dc_id=2, init=ClientInit(api_id=1, api_hash="x"))
    c._transport = object()  # type: ignore[attr-defined]
    c._sender = object()  # type: ignore[attr-defined]
    c._state = object()  # type: ignore[attr-defined]
    return c


# ===================== Scheduled Messages Tests =====================


def test_get_scheduled_messages_calls_correct_tl() -> None:
    """get_scheduled_messages should call messages.getScheduledHistory."""
    c = _make_connected_client()
    c.entities.user_access_hash[123] = 456

    seen: list[Any] = []

    async def invoke_api(req: Any, *, timeout: float = 0) -> Any:
        seen.append(req)
        return type("_R", (), {"messages": [], "users": [], "chats": []})()

    c.invoke_api = invoke_api  # type: ignore[assignment]

    result = asyncio.run(c.get_scheduled_messages(("user", 123)))
    assert isinstance(result, list)
    assert len(seen) == 1
    assert getattr(seen[0], "TL_NAME", None) == "messages.getScheduledHistory"


def test_delete_scheduled_messages_calls_correct_tl() -> None:
    """delete_scheduled_messages should call messages.deleteScheduledMessages."""
    c = _make_connected_client()
    c.entities.user_access_hash[123] = 456

    seen: list[Any] = []

    async def invoke_api(req: Any, *, timeout: float = 0) -> Any:
        seen.append(req)
        return type("_R", (), {"users": [], "chats": []})()

    c.invoke_api = invoke_api  # type: ignore[assignment]

    result = asyncio.run(c.delete_scheduled_messages(("user", 123), [1, 2, 3]))
    assert result is not None
    assert len(seen) == 1
    assert getattr(seen[0], "TL_NAME", None) == "messages.deleteScheduledMessages"
    assert getattr(seen[0], "id", None) == [1, 2, 3]


def test_send_scheduled_now_calls_correct_tl() -> None:
    """send_scheduled_now should call messages.sendScheduledMessages."""
    c = _make_connected_client()
    c.entities.user_access_hash[123] = 456

    seen: list[Any] = []

    async def invoke_api(req: Any, *, timeout: float = 0) -> Any:
        seen.append(req)
        return type("_R", (), {"users": [], "chats": []})()

    c.invoke_api = invoke_api  # type: ignore[assignment]

    result = asyncio.run(c.send_scheduled_now(("user", 123), 42))
    assert result is not None
    assert len(seen) == 1
    assert getattr(seen[0], "TL_NAME", None) == "messages.sendScheduledMessages"
    assert getattr(seen[0], "id", None) == [42]


# ===================== Poll Tests =====================


def test_send_poll_creates_input_media_poll() -> None:
    """send_poll should create an InputMediaPoll and call messages.sendMedia."""
    c = _make_connected_client()
    c.entities.user_access_hash[123] = 456

    seen: list[Any] = []

    async def invoke_api(req: Any, *, timeout: float = 0) -> Any:
        seen.append(req)
        return type("_R", (), {"users": [], "chats": []})()

    c.invoke_api = invoke_api  # type: ignore[assignment]

    result = asyncio.run(
        c.send_poll(
            ("user", 123),
            "What is your favorite color?",
            ["Red", "Blue", "Green"],
        )
    )
    assert result is not None
    assert len(seen) == 1
    assert getattr(seen[0], "TL_NAME", None) == "messages.sendMedia"

    media = getattr(seen[0], "media", None)
    assert media is not None
    assert getattr(media, "TL_NAME", None) == "inputMediaPoll"


def test_send_poll_requires_at_least_2_options() -> None:
    """send_poll should raise error with less than 2 options."""
    c = _make_connected_client()
    c.entities.user_access_hash[123] = 456

    async def invoke_api(req: Any, *, timeout: float = 0) -> Any:
        return type("_R", (), {"users": [], "chats": []})()

    c.invoke_api = invoke_api  # type: ignore[assignment]

    import pytest

    with pytest.raises(Exception, match="at least 2 options"):
        asyncio.run(c.send_poll(("user", 123), "Question?", ["Only one"]))


def test_send_quiz_sets_quiz_flag() -> None:
    """send_quiz should set quiz=True in the poll."""
    c = _make_connected_client()
    c.entities.user_access_hash[123] = 456

    seen: list[Any] = []

    async def invoke_api(req: Any, *, timeout: float = 0) -> Any:
        seen.append(req)
        return type("_R", (), {"users": [], "chats": []})()

    c.invoke_api = invoke_api  # type: ignore[assignment]

    result = asyncio.run(
        c.send_quiz(
            ("user", 123),
            "2 + 2 = ?",
            ["3", "4", "5"],
            correct_option=1,  # "4" is correct
            explanation="Basic math!",
        )
    )
    assert result is not None
    assert len(seen) == 1

    media = getattr(seen[0], "media", None)
    poll = getattr(media, "poll", None)
    assert getattr(poll, "quiz", None) is True


def test_vote_poll_calls_messages_send_vote() -> None:
    """vote_poll should call messages.sendVote."""
    c = _make_connected_client()
    c.entities.user_access_hash[123] = 456

    seen: list[Any] = []

    async def invoke_api(req: Any, *, timeout: float = 0) -> Any:
        seen.append(req)
        return type("_R", (), {"users": [], "chats": []})()

    c.invoke_api = invoke_api  # type: ignore[assignment]

    result = asyncio.run(c.vote_poll(("user", 123), msg_id=42, options=1))
    assert result is not None
    assert len(seen) == 1
    assert getattr(seen[0], "TL_NAME", None) == "messages.sendVote"
    assert getattr(seen[0], "msg_id", None) == 42


def test_get_poll_results_calls_correct_tl() -> None:
    """get_poll_results should call messages.getPollResults."""
    c = _make_connected_client()
    c.entities.user_access_hash[123] = 456

    seen: list[Any] = []

    async def invoke_api(req: Any, *, timeout: float = 0) -> Any:
        seen.append(req)
        return type("_R", (), {"users": [], "chats": []})()

    c.invoke_api = invoke_api  # type: ignore[assignment]

    result = asyncio.run(c.get_poll_results(("user", 123), msg_id=42))
    assert result is not None
    assert len(seen) == 1
    assert getattr(seen[0], "TL_NAME", None) == "messages.getPollResults"
