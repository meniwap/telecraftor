"""Tests for delete_messages functionality."""

from __future__ import annotations

import inspect


class TestDeleteMessages:
    def test_delete_messages_signature(self):
        """Test that delete_messages has the expected signature."""
        from telecraft.client.mtproto import MtprotoClient

        sig = inspect.signature(MtprotoClient.delete_messages)
        params = sig.parameters

        assert "peer" in params
        assert "msg_ids" in params
        assert "revoke" in params
        assert params["revoke"].default is True
        assert "timeout" in params

    def test_messages_delete_messages_tl_exists(self):
        """Test that the TL function exists for regular messages."""
        from telecraft.tl.generated.functions import MessagesDeleteMessages

        assert hasattr(MessagesDeleteMessages, "TL_NAME")
        assert MessagesDeleteMessages.TL_NAME == "messages.deleteMessages"

        tl_params = dict(MessagesDeleteMessages.TL_PARAMS)
        assert "revoke" in tl_params
        assert "id" in tl_params

    def test_channels_delete_messages_tl_exists(self):
        """Test that the TL function exists for channel messages."""
        from telecraft.tl.generated.functions import ChannelsDeleteMessages

        assert hasattr(ChannelsDeleteMessages, "TL_NAME")
        assert ChannelsDeleteMessages.TL_NAME == "channels.deleteMessages"

        tl_params = dict(ChannelsDeleteMessages.TL_PARAMS)
        assert "channel" in tl_params
        assert "id" in tl_params
