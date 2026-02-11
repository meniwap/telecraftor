from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal

from telecraft.tl.generated.types import (
    InputPrivacyKeyAbout,
    InputPrivacyKeyAddedByPhone,
    InputPrivacyKeyBirthday,
    InputPrivacyKeyChatInvite,
    InputPrivacyKeyForwards,
    InputPrivacyKeyNoPaidMessages,
    InputPrivacyKeyPhoneCall,
    InputPrivacyKeyPhoneNumber,
    InputPrivacyKeyPhoneP2P,
    InputPrivacyKeyProfilePhoto,
    InputPrivacyKeySavedMusic,
    InputPrivacyKeyStarGiftsAutoSave,
    InputPrivacyKeyStatusTimestamp,
    InputPrivacyKeyVoiceMessages,
    InputPrivacyValueAllowAll,
    InputPrivacyValueAllowBots,
    InputPrivacyValueAllowChatParticipants,
    InputPrivacyValueAllowCloseFriends,
    InputPrivacyValueAllowContacts,
    InputPrivacyValueAllowPremium,
    InputPrivacyValueAllowUsers,
    InputPrivacyValueDisallowAll,
    InputPrivacyValueDisallowBots,
    InputPrivacyValueDisallowChatParticipants,
    InputPrivacyValueDisallowContacts,
    InputPrivacyValueDisallowUsers,
)

PrivacyKey = Literal[
    "status_timestamp",
    "chat_invite",
    "phone_call",
    "phone_p2p",
    "forwards",
    "profile_photo",
    "phone_number",
    "added_by_phone",
    "voice_messages",
    "about",
    "birthday",
    "star_gifts_auto_save",
    "no_paid_messages",
    "saved_music",
]


def build_input_privacy_key(key: PrivacyKey | Any) -> Any:
    if not isinstance(key, str):
        return key
    mapping: dict[str, Any] = {
        "status_timestamp": InputPrivacyKeyStatusTimestamp,
        "chat_invite": InputPrivacyKeyChatInvite,
        "phone_call": InputPrivacyKeyPhoneCall,
        "phone_p2p": InputPrivacyKeyPhoneP2P,
        "forwards": InputPrivacyKeyForwards,
        "profile_photo": InputPrivacyKeyProfilePhoto,
        "phone_number": InputPrivacyKeyPhoneNumber,
        "added_by_phone": InputPrivacyKeyAddedByPhone,
        "voice_messages": InputPrivacyKeyVoiceMessages,
        "about": InputPrivacyKeyAbout,
        "birthday": InputPrivacyKeyBirthday,
        "star_gifts_auto_save": InputPrivacyKeyStarGiftsAutoSave,
        "no_paid_messages": InputPrivacyKeyNoPaidMessages,
        "saved_music": InputPrivacyKeySavedMusic,
    }
    try:
        return mapping[key]()
    except KeyError as e:
        raise ValueError(f"Unsupported privacy key {key!r}") from e


class PrivacyRuleBuilder:
    @staticmethod
    def allow_all() -> Any:
        return InputPrivacyValueAllowAll()

    @staticmethod
    def disallow_all() -> Any:
        return InputPrivacyValueDisallowAll()

    @staticmethod
    def allow_contacts() -> Any:
        return InputPrivacyValueAllowContacts()

    @staticmethod
    def disallow_contacts() -> Any:
        return InputPrivacyValueDisallowContacts()

    @staticmethod
    def allow_users(users: Sequence[Any]) -> Any:
        return InputPrivacyValueAllowUsers(users=list(users))

    @staticmethod
    def disallow_users(users: Sequence[Any]) -> Any:
        return InputPrivacyValueDisallowUsers(users=list(users))

    @staticmethod
    def allow_chat_participants(chats: Sequence[int]) -> Any:
        return InputPrivacyValueAllowChatParticipants(chats=[int(chat) for chat in chats])

    @staticmethod
    def disallow_chat_participants(chats: Sequence[int]) -> Any:
        return InputPrivacyValueDisallowChatParticipants(chats=[int(chat) for chat in chats])

    @staticmethod
    def allow_close_friends() -> Any:
        return InputPrivacyValueAllowCloseFriends()

    @staticmethod
    def allow_premium() -> Any:
        return InputPrivacyValueAllowPremium()

    @staticmethod
    def allow_bots() -> Any:
        return InputPrivacyValueAllowBots()

    @staticmethod
    def disallow_bots() -> Any:
        return InputPrivacyValueDisallowBots()
