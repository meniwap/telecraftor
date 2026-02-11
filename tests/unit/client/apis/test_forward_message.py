"""Tests for forward_messages functionality."""

from __future__ import annotations

import inspect


class TestForwardMessages:
    def test_forward_messages_signature(self):
        """Test that forward_messages has the expected signature."""
        from telecraft.client.mtproto import MtprotoClient

        sig = inspect.signature(MtprotoClient.forward_messages)
        params = sig.parameters

        assert "from_peer" in params
        assert "to_peer" in params
        assert "msg_ids" in params
        assert "silent" in params
        assert params["silent"].default is False
        assert "drop_author" in params
        assert params["drop_author"].default is False
        assert "drop_captions" in params
        assert params["drop_captions"].default is False
        assert "timeout" in params

    def test_messages_forward_messages_tl_exists(self):
        """Test that the TL function exists and has correct structure."""
        from telecraft.tl.generated.functions import MessagesForwardMessages

        assert hasattr(MessagesForwardMessages, "TL_NAME")
        assert MessagesForwardMessages.TL_NAME == "messages.forwardMessages"

        # Check important fields exist
        tl_params = dict(MessagesForwardMessages.TL_PARAMS)
        assert "from_peer" in tl_params
        assert "to_peer" in tl_params
        assert "id" in tl_params
        assert "random_id" in tl_params
        assert "silent" in tl_params
        assert "drop_author" in tl_params
        assert "drop_media_captions" in tl_params
