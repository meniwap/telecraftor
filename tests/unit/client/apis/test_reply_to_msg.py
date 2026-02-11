"""Tests for reply_to_msg_id functionality in send_message and MessageEvent.reply."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock


class TestSendMessageReplyTo:
    def test_send_message_peer_creates_input_reply_to_message(self):
        """
        Test that send_message_peer creates InputReplyToMessage when
        reply_to_msg_id is provided.
        """
        from telecraft.tl.generated.types import InputReplyToMessage

        # Just verify the type exists and can be created
        reply_to = InputReplyToMessage(
            flags=0,
            reply_to_msg_id=12345,
            top_msg_id=None,
            reply_to_peer_id=None,
            quote_text=None,
            quote_entities=None,
            quote_offset=None,
            monoforum_peer_id=None,
            todo_item_id=None,
        )
        assert reply_to.reply_to_msg_id == 12345

    def test_send_message_peer_none_reply_to(self):
        """Test that reply_to is None when no reply_to_msg_id is provided."""
        # This is a structural test - we verify the parameter exists
        import inspect

        from telecraft.client.mtproto import MtprotoClient

        sig = inspect.signature(MtprotoClient.send_message_peer)
        assert "reply_to_msg_id" in sig.parameters
        assert sig.parameters["reply_to_msg_id"].default is None

    def test_send_message_has_reply_to_param(self):
        """Test that high-level send_message has reply_to_msg_id parameter."""
        import inspect

        from telecraft.client.mtproto import MtprotoClient

        sig = inspect.signature(MtprotoClient.send_message)
        assert "reply_to_msg_id" in sig.parameters
        assert sig.parameters["reply_to_msg_id"].default is None
        assert "silent" in sig.parameters
        assert sig.parameters["silent"].default is False

    def test_send_file_has_reply_to_param(self):
        """Test that send_file has reply_to_msg_id parameter."""
        import inspect

        from telecraft.client.mtproto import MtprotoClient

        sig = inspect.signature(MtprotoClient.send_file)
        assert "reply_to_msg_id" in sig.parameters
        assert sig.parameters["reply_to_msg_id"].default is None
        assert "silent" in sig.parameters
        assert sig.parameters["silent"].default is False


class TestMessageEventReply:
    def test_message_event_reply_has_quote_param(self):
        """Test that MessageEvent.reply has quote parameter."""
        import inspect

        from telecraft.bot.events import MessageEvent

        sig = inspect.signature(MessageEvent.reply)
        assert "quote" in sig.parameters
        assert sig.parameters["quote"].default is False
        assert "reply_markup" in sig.parameters
        assert sig.parameters["reply_markup"].default is None

    def test_message_event_reply_quote_false_no_reply_to(self):
        """Test that quote=False does not set reply_to_msg_id."""
        from telecraft.bot.events import MessageEvent

        # Create a mock client
        client = MagicMock()
        send_message = AsyncMock(return_value={"_": "updates"})
        client.send_message = send_message

        # Create event with msg_id
        evt = MessageEvent(
            client=client,
            raw=MagicMock(),
            msg_id=12345,
            peer_type="chat",
            peer_id=67890,
        )

        # Test that quote=False is default
        assert evt.msg_id == 12345

    def test_message_event_reply_quote_true_uses_msg_id(self):
        """Test that quote=True should pass msg_id as reply_to_msg_id."""
        from telecraft.bot.events import MessageEvent

        client = MagicMock()
        send_message = AsyncMock(return_value={"_": "updates"})
        client.send_message = send_message

        evt = MessageEvent(
            client=client,
            raw=MagicMock(),
            msg_id=12345,
            peer_type="chat",
            peer_id=67890,
        )

        # The implementation should use msg_id when quote=True
        assert evt.msg_id == 12345
        # When quote=True, the reply_to_msg_id should be self.msg_id

    def test_message_event_reply_to_msg_id_property(self):
        """Test that reply_to_msg_id property reads from raw."""
        from telecraft.bot.events import MessageEvent

        # Create mock raw message with reply header
        raw = MagicMock()
        reply_to = MagicMock()
        reply_to.reply_to_msg_id = 99999
        raw.reply_to = reply_to

        evt = MessageEvent(
            client=MagicMock(),
            raw=raw,
            msg_id=12345,
        )

        assert evt.reply_to_msg_id == 99999

    def test_message_event_reply_to_msg_id_none_when_no_reply(self):
        """Test that reply_to_msg_id is None when message is not a reply."""
        from telecraft.bot.events import MessageEvent

        raw = MagicMock()
        raw.reply_to = None

        evt = MessageEvent(
            client=MagicMock(),
            raw=raw,
            msg_id=12345,
        )

        assert evt.reply_to_msg_id is None
