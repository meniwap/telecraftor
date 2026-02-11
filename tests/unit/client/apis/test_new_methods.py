"""Tests for new client methods: edit, pin, search, reactions, participants."""

from __future__ import annotations

import inspect


class TestEditMessage:
    def test_edit_message_signature(self):
        """Test that edit_message has the expected signature."""
        from telecraft.client.mtproto import MtprotoClient

        sig = inspect.signature(MtprotoClient.edit_message)
        params = sig.parameters

        assert "peer" in params
        assert "msg_id" in params
        assert "text" in params
        assert "no_webpage" in params
        assert params["no_webpage"].default is False

    def test_messages_edit_message_tl_exists(self):
        """Test that the TL function exists."""
        from telecraft.tl.generated.functions import MessagesEditMessage

        assert hasattr(MessagesEditMessage, "TL_NAME")
        assert MessagesEditMessage.TL_NAME == "messages.editMessage"


class TestPinMessage:
    def test_pin_message_signature(self):
        """Test that pin_message has the expected signature."""
        from telecraft.client.mtproto import MtprotoClient

        sig = inspect.signature(MtprotoClient.pin_message)
        params = sig.parameters

        assert "peer" in params
        assert "msg_id" in params
        assert "silent" in params
        assert params["silent"].default is False
        assert "unpin" in params
        assert params["unpin"].default is False

    def test_messages_update_pinned_message_tl_exists(self):
        """Test that the TL function exists."""
        from telecraft.tl.generated.functions import MessagesUpdatePinnedMessage

        assert hasattr(MessagesUpdatePinnedMessage, "TL_NAME")
        assert MessagesUpdatePinnedMessage.TL_NAME == "messages.updatePinnedMessage"


class TestSendReaction:
    def test_send_reaction_signature(self):
        """Test that send_reaction has the expected signature."""
        from telecraft.client.mtproto import MtprotoClient

        sig = inspect.signature(MtprotoClient.send_reaction)
        params = sig.parameters

        assert "peer" in params
        assert "msg_id" in params
        assert "reaction" in params
        assert "big" in params
        assert params["big"].default is False

    def test_reaction_emoji_type_exists(self):
        """Test that ReactionEmoji type exists."""
        from telecraft.tl.generated.types import ReactionEmoji

        # Create a reaction
        r = ReactionEmoji(emoticon="👍")
        assert r.emoticon == "👍"


class TestSearchMessages:
    def test_search_messages_signature(self):
        """Test that search_messages has the expected signature."""
        from telecraft.client.mtproto import MtprotoClient

        sig = inspect.signature(MtprotoClient.search_messages)
        params = sig.parameters

        assert "peer" in params
        assert "query" in params
        assert params["query"].default == ""
        assert "limit" in params
        assert params["limit"].default == 100
        assert "from_user" in params
        assert "min_date" in params
        assert "max_date" in params

    def test_messages_search_tl_exists(self):
        """Test that the TL function exists."""
        from telecraft.tl.generated.functions import MessagesSearch

        assert hasattr(MessagesSearch, "TL_NAME")
        assert MessagesSearch.TL_NAME == "messages.search"


class TestIterParticipants:
    def test_iter_participants_signature(self):
        """Test that iter_participants has the expected signature."""
        from telecraft.client.mtproto import MtprotoClient

        sig = inspect.signature(MtprotoClient.iter_participants)
        params = sig.parameters

        assert "channel" in params
        assert "limit" in params
        assert params["limit"].default is None
        assert "filter_type" in params
        assert params["filter_type"].default == "recent"

    def test_channels_get_participants_tl_exists(self):
        """Test that the TL function exists."""
        from telecraft.tl.generated.functions import ChannelsGetParticipants

        assert hasattr(ChannelsGetParticipants, "TL_NAME")
        assert ChannelsGetParticipants.TL_NAME == "channels.getParticipants"

    def test_participant_filters_exist(self):
        """Test that participant filter types exist."""
        from telecraft.tl.generated.types import (
            ChannelParticipantsAdmins,
            ChannelParticipantsBanned,
            ChannelParticipantsBots,
            ChannelParticipantsKicked,
            ChannelParticipantsRecent,
        )

        # Just verify they can be instantiated
        assert ChannelParticipantsRecent() is not None
        assert ChannelParticipantsAdmins() is not None
        assert ChannelParticipantsBots() is not None
        assert ChannelParticipantsBanned(q="") is not None
        assert ChannelParticipantsKicked(q="") is not None


class TestGetUserInfo:
    def test_get_user_info_signature(self):
        """Test that get_user_info has the expected signature."""
        from telecraft.client.mtproto import MtprotoClient

        sig = inspect.signature(MtprotoClient.get_user_info)
        params = sig.parameters

        assert "user" in params
        assert "timeout" in params


class TestGetChatInfo:
    def test_get_chat_info_signature(self):
        """Test that get_chat_info has the expected signature."""
        from telecraft.client.mtproto import MtprotoClient

        sig = inspect.signature(MtprotoClient.get_chat_info)
        params = sig.parameters

        assert "chat" in params
        assert "timeout" in params


class TestJoinLeaveChannel:
    def test_join_channel_signature(self):
        """Test that join_channel has the expected signature."""
        from telecraft.client.mtproto import MtprotoClient

        sig = inspect.signature(MtprotoClient.join_channel)
        params = sig.parameters

        assert "channel" in params

    def test_leave_channel_signature(self):
        """Test that leave_channel has the expected signature."""
        from telecraft.client.mtproto import MtprotoClient

        sig = inspect.signature(MtprotoClient.leave_channel)
        params = sig.parameters

        assert "channel" in params


class TestSendAction:
    def test_send_action_signature(self):
        """Test that send_action has the expected signature."""
        from telecraft.client.mtproto import MtprotoClient

        sig = inspect.signature(MtprotoClient.send_action)
        params = sig.parameters

        assert "peer" in params
        assert "action" in params
        assert params["action"].default == "typing"

    def test_action_types_exist(self):
        """Test that typing action types exist."""
        from telecraft.tl.generated.types import (
            SendMessageCancelAction,
            SendMessageRecordAudioAction,
            SendMessageTypingAction,
        )

        assert SendMessageTypingAction() is not None
        assert SendMessageRecordAudioAction() is not None
        assert SendMessageCancelAction() is not None


class TestGetProfilePhotos:
    def test_get_profile_photos_signature(self):
        """Test that get_profile_photos has the expected signature."""
        from telecraft.client.mtproto import MtprotoClient

        sig = inspect.signature(MtprotoClient.get_profile_photos)
        params = sig.parameters

        assert "user" in params
        assert "limit" in params
        assert params["limit"].default == 100
