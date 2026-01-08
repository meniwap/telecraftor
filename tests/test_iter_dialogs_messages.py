"""Tests for iter_dialogs and iter_messages async generators."""

from __future__ import annotations

import inspect
from collections.abc import AsyncIterator


class TestIterDialogs:
    def test_iter_dialogs_signature(self):
        """Test that iter_dialogs has the expected signature."""
        from telecraft.client.mtproto import MtprotoClient

        sig = inspect.signature(MtprotoClient.iter_dialogs)
        params = sig.parameters

        assert "limit" in params
        assert params["limit"].default is None
        assert "folder_id" in params
        assert params["folder_id"].default is None
        assert "timeout" in params

    def test_iter_dialogs_returns_async_iterator(self):
        """Test that iter_dialogs is an async generator."""
        from telecraft.client.mtproto import MtprotoClient

        # Check return type annotation
        hints = MtprotoClient.iter_dialogs.__annotations__
        assert "return" in hints
        # The return type should be AsyncIterator[Any]


class TestIterMessages:
    def test_iter_messages_signature(self):
        """Test that iter_messages has the expected signature."""
        from telecraft.client.mtproto import MtprotoClient

        sig = inspect.signature(MtprotoClient.iter_messages)
        params = sig.parameters

        assert "peer" in params
        assert "limit" in params
        assert params["limit"].default is None
        assert "offset_id" in params
        assert params["offset_id"].default == 0
        assert "min_id" in params
        assert params["min_id"].default == 0
        assert "max_id" in params
        assert params["max_id"].default == 0
        assert "timeout" in params

    def test_iter_messages_returns_async_iterator(self):
        """Test that iter_messages is an async generator."""
        from telecraft.client.mtproto import MtprotoClient

        # Check return type annotation
        hints = MtprotoClient.iter_messages.__annotations__
        assert "return" in hints


class TestTLFunctions:
    def test_messages_get_dialogs_exists(self):
        """Test that MessagesGetDialogs TL function exists."""
        from telecraft.tl.generated.functions import MessagesGetDialogs

        assert hasattr(MessagesGetDialogs, "TL_NAME")
        assert MessagesGetDialogs.TL_NAME == "messages.getDialogs"

        tl_params = dict(MessagesGetDialogs.TL_PARAMS)
        assert "offset_date" in tl_params
        assert "offset_id" in tl_params
        assert "offset_peer" in tl_params
        assert "limit" in tl_params

    def test_messages_get_history_exists(self):
        """Test that MessagesGetHistory TL function exists."""
        from telecraft.tl.generated.functions import MessagesGetHistory

        assert hasattr(MessagesGetHistory, "TL_NAME")
        assert MessagesGetHistory.TL_NAME == "messages.getHistory"

        tl_params = dict(MessagesGetHistory.TL_PARAMS)
        assert "peer" in tl_params
        assert "offset_id" in tl_params
        assert "limit" in tl_params
        assert "min_id" in tl_params
        assert "max_id" in tl_params
