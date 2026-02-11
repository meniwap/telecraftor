from __future__ import annotations

from .admin import AdminAPI
from .business import BusinessAPI, BusinessLinksAPI, BusinessProfileAPI, BusinessQuickRepliesAPI
from .channels import ChannelsAPI, ChannelSettingsAPI
from .chatlists import ChatlistInvitesAPI, ChatlistsAPI, ChatlistSuggestionsAPI, ChatlistUpdatesAPI
from .chats import ChatsAPI
from .contacts import ContactsAPI
from .dialogs import DialogsAPI, DialogsFiltersAPI, DialogsPinnedAPI, DialogsUnreadAPI
from .folders import FoldersAPI
from .games import GamesAPI, GameScoresAPI
from .gifts import GiftsAPI, GiftsResaleAPI, GiftsSavedAPI, GiftsUniqueAPI
from .media import MediaAPI
from .messages import MessagesAPI
from .notifications import (
    NotificationsAPI,
    NotificationsContactSignupAPI,
    NotificationsReactionsAPI,
)
from .peers import PeersAPI
from .polls import PollsAPI
from .presence import PresenceAPI
from .privacy import PrivacyAPI, PrivacyGlobalSettingsAPI
from .profile import ProfileAPI
from .reactions import ReactionsAPI
from .saved import (
    SavedAPI,
    SavedDialogsAPI,
    SavedGifsAPI,
    SavedHistoryAPI,
    SavedPinnedAPI,
    SavedReactionTagsAPI,
)
from .stars import StarsAPI, StarsFormsAPI, StarsRevenueAPI, StarsTransactionsAPI
from .stickers import (
    StickerEmojiAPI,
    StickerFavoritesAPI,
    StickerRecentAPI,
    StickersAPI,
    StickerSearchAPI,
    StickerSetsAPI,
)
from .stories import StoriesAPI, StoriesCapabilitiesAPI, StoriesFeedAPI
from .topics import TopicsAPI, TopicsForumAPI
from .updates import UpdatesAPI

__all__ = [
    "AdminAPI",
    "BusinessAPI",
    "BusinessLinksAPI",
    "BusinessProfileAPI",
    "BusinessQuickRepliesAPI",
    "ChannelSettingsAPI",
    "ChannelsAPI",
    "ChatlistInvitesAPI",
    "ChatlistSuggestionsAPI",
    "ChatlistUpdatesAPI",
    "ChatlistsAPI",
    "ChatsAPI",
    "ContactsAPI",
    "DialogsAPI",
    "DialogsFiltersAPI",
    "DialogsPinnedAPI",
    "DialogsUnreadAPI",
    "FoldersAPI",
    "GameScoresAPI",
    "GamesAPI",
    "GiftsAPI",
    "GiftsResaleAPI",
    "GiftsSavedAPI",
    "GiftsUniqueAPI",
    "MediaAPI",
    "MessagesAPI",
    "NotificationsAPI",
    "NotificationsContactSignupAPI",
    "NotificationsReactionsAPI",
    "PeersAPI",
    "PollsAPI",
    "PresenceAPI",
    "PrivacyAPI",
    "PrivacyGlobalSettingsAPI",
    "ProfileAPI",
    "ReactionsAPI",
    "SavedAPI",
    "SavedDialogsAPI",
    "SavedGifsAPI",
    "SavedHistoryAPI",
    "SavedPinnedAPI",
    "SavedReactionTagsAPI",
    "StickerEmojiAPI",
    "StickerFavoritesAPI",
    "StickerRecentAPI",
    "StickerSearchAPI",
    "StickerSetsAPI",
    "StickersAPI",
    "StarsAPI",
    "StarsFormsAPI",
    "StarsRevenueAPI",
    "StarsTransactionsAPI",
    "StoriesAPI",
    "StoriesCapabilitiesAPI",
    "StoriesFeedAPI",
    "TopicsAPI",
    "TopicsForumAPI",
    "UpdatesAPI",
]
