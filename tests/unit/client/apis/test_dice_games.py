"""
Tests for dice and game features.
"""

import asyncio
import inspect
from typing import Any

import pytest

from telecraft.client.mtproto import ClientInit, MtprotoClient, MtprotoClientError
from telecraft.tl.generated.types import InputMediaDice


def _make_connected_client() -> MtprotoClient:
    c = MtprotoClient(network="test", dc_id=2, init=ClientInit(api_id=1, api_hash="x"))
    c._transport = object()  # type: ignore[attr-defined]
    c._sender = object()  # type: ignore[attr-defined]
    c._state = object()  # type: ignore[attr-defined]
    return c


class TestSendDice:
    def test_send_dice_signature(self) -> None:
        sig = inspect.signature(MtprotoClient.send_dice)
        assert "peer" in sig.parameters
        assert "emoji" in sig.parameters
        assert "reply_to_msg_id" in sig.parameters
        assert "silent" in sig.parameters

    def test_send_dice_default_emoji_is_dice(self) -> None:
        sig = inspect.signature(MtprotoClient.send_dice)
        assert sig.parameters["emoji"].default == "🎲"

    def test_send_dice_creates_input_media_dice(self) -> None:
        c = _make_connected_client()
        c.entities.user_access_hash[123] = 456
        seen: list[Any] = []

        async def invoke_api(req: Any, *, timeout: float = 0) -> Any:
            seen.append(req)
            return type("_R", (), {"users": [], "chats": []})()

        c.invoke_api = invoke_api  # type: ignore[assignment]

        asyncio.run(c.send_dice(("user", 123), "🎲"))

        assert len(seen) == 1
        req = seen[0]
        assert getattr(req, "TL_NAME", None) == "messages.sendMedia"
        assert getattr(req.media, "TL_NAME", None) == "inputMediaDice"
        assert req.media.emoticon == "🎲"

    def test_send_dice_supports_all_emoji(self) -> None:
        c = _make_connected_client()
        c.entities.user_access_hash[123] = 456
        seen: list[Any] = []

        async def invoke_api(req: Any, *, timeout: float = 0) -> Any:
            seen.append(req)
            return type("_R", (), {"users": [], "chats": []})()

        c.invoke_api = invoke_api  # type: ignore[assignment]

        for emoji in ["🎲", "🎯", "🏀", "⚽", "🎳", "🎰"]:
            seen.clear()
            asyncio.run(c.send_dice(("user", 123), emoji))
            assert len(seen) == 1
            assert seen[0].media.emoticon == emoji

    def test_send_dice_rejects_unsupported_emoji(self) -> None:
        c = _make_connected_client()
        c.entities.user_access_hash[123] = 456

        with pytest.raises(MtprotoClientError, match="unsupported emoji"):
            asyncio.run(c.send_dice(("user", 123), "❤️"))


class TestDiceShortcuts:
    def test_roll_dice_exists(self) -> None:
        assert hasattr(MtprotoClient, "roll_dice")
        sig = inspect.signature(MtprotoClient.roll_dice)
        assert "peer" in sig.parameters

    def test_throw_darts_exists(self) -> None:
        assert hasattr(MtprotoClient, "throw_darts")

    def test_shoot_basketball_exists(self) -> None:
        assert hasattr(MtprotoClient, "shoot_basketball")

    def test_kick_football_exists(self) -> None:
        assert hasattr(MtprotoClient, "kick_football")

    def test_roll_bowling_exists(self) -> None:
        assert hasattr(MtprotoClient, "roll_bowling")

    def test_spin_slot_machine_exists(self) -> None:
        assert hasattr(MtprotoClient, "spin_slot_machine")

    def test_shortcut_calls_send_dice(self) -> None:
        c = _make_connected_client()
        c.entities.user_access_hash[123] = 456
        seen: list[Any] = []

        async def invoke_api(req: Any, *, timeout: float = 0) -> Any:
            seen.append(req)
            return type("_R", (), {"users": [], "chats": []})()

        c.invoke_api = invoke_api  # type: ignore[assignment]

        # Test roll_dice uses 🎲
        asyncio.run(c.roll_dice(("user", 123)))
        assert seen[-1].media.emoticon == "🎲"

        # Test throw_darts uses 🎯
        asyncio.run(c.throw_darts(("user", 123)))
        assert seen[-1].media.emoticon == "🎯"

        # Test shoot_basketball uses 🏀
        asyncio.run(c.shoot_basketball(("user", 123)))
        assert seen[-1].media.emoticon == "🏀"

        # Test kick_football uses ⚽
        asyncio.run(c.kick_football(("user", 123)))
        assert seen[-1].media.emoticon == "⚽"

        # Test roll_bowling uses 🎳
        asyncio.run(c.roll_bowling(("user", 123)))
        assert seen[-1].media.emoticon == "🎳"

        # Test spin_slot_machine uses 🎰
        asyncio.run(c.spin_slot_machine(("user", 123)))
        assert seen[-1].media.emoticon == "🎰"


class TestInputMediaDice:
    def test_input_media_dice_exists(self) -> None:
        assert InputMediaDice.__name__ == "InputMediaDice"

    def test_input_media_dice_has_emoticon(self) -> None:
        dice = InputMediaDice(emoticon="🎲")
        assert dice.emoticon == "🎲"
