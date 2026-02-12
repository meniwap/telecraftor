from __future__ import annotations

from .account import (
    AccountAPI,
    AccountContentAPI,
    AccountSessionsAPI,
    AccountTermsAPI,
    AccountThemesAPI,
    AccountTTLAPI,
    AccountWallpapersAPI,
    AccountWebSessionsAPI,
)
from .admin import AdminAPI
from .business import BusinessAPI, BusinessLinksAPI, BusinessProfileAPI, BusinessQuickRepliesAPI
from .calls import CallsAPI, CallsConferenceAPI, CallsGroupAPI, CallsStreamAPI
from .channels import ChannelAdminLogAPI, ChannelLinksAPI, ChannelsAPI, ChannelSettingsAPI
from .chatlists import ChatlistInvitesAPI, ChatlistsAPI, ChatlistSuggestionsAPI, ChatlistUpdatesAPI
from .chats import ChatsAPI
from .contacts import ContactsAPI
from .dialogs import DialogsAPI, DialogsFiltersAPI, DialogsPinnedAPI, DialogsUnreadAPI
from .discovery import DiscoveryAPI, DiscoveryBotsAPI, DiscoveryChannelsAPI
from .drafts import DraftsAPI
from .folders import FoldersAPI
from .games import GamesAPI, GameScoresAPI
from .gifts import GiftsAPI, GiftsResaleAPI, GiftsSavedAPI, GiftsUniqueAPI
from .media import MediaAPI
from .messages import MessagesAPI, MessagesScheduledAPI
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
from .reports import ReportsAPI
from .saved import (
    SavedAPI,
    SavedDialogsAPI,
    SavedGifsAPI,
    SavedHistoryAPI,
    SavedPinnedAPI,
    SavedReactionTagsAPI,
)
from .search import SearchAPI
from .stars import StarsAPI, StarsFormsAPI, StarsRevenueAPI, StarsTransactionsAPI
from .stats import StatsAPI, StatsChannelsAPI, StatsGraphAPI, StatsPublicForwardsAPI
from .stickers import (
    StickerEmojiAPI,
    StickerFavoritesAPI,
    StickerRecentAPI,
    StickersAPI,
    StickerSearchAPI,
    StickerSetsAPI,
)
from .stories import StoriesAPI, StoriesCapabilitiesAPI, StoriesFeedAPI
from .takeout import TakeoutAPI, TakeoutMediaAPI, TakeoutMessagesAPI
from .todos import TodosAPI
from .topics import TopicsAPI, TopicsForumAPI
from .translate import TranslateAPI
from .updates import UpdatesAPI
from .webapps import WebAppsAPI

__all__ = [
    "AccountAPI",
    "AccountContentAPI",
    "AccountSessionsAPI",
    "AccountTermsAPI",
    "AccountThemesAPI",
    "AccountTTLAPI",
    "AccountWallpapersAPI",
    "AccountWebSessionsAPI",
    "AdminAPI",
    "BusinessAPI",
    "BusinessLinksAPI",
    "BusinessProfileAPI",
    "BusinessQuickRepliesAPI",
    "CallsAPI",
    "CallsConferenceAPI",
    "CallsGroupAPI",
    "CallsStreamAPI",
    "ChannelAdminLogAPI",
    "ChannelLinksAPI",
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
    "DiscoveryAPI",
    "DiscoveryBotsAPI",
    "DiscoveryChannelsAPI",
    "DraftsAPI",
    "FoldersAPI",
    "GameScoresAPI",
    "GamesAPI",
    "GiftsAPI",
    "GiftsResaleAPI",
    "GiftsSavedAPI",
    "GiftsUniqueAPI",
    "MediaAPI",
    "MessagesAPI",
    "MessagesScheduledAPI",
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
    "ReportsAPI",
    "SavedAPI",
    "SavedDialogsAPI",
    "SavedGifsAPI",
    "SavedHistoryAPI",
    "SavedPinnedAPI",
    "SavedReactionTagsAPI",
    "SearchAPI",
    "StarsAPI",
    "StarsFormsAPI",
    "StarsRevenueAPI",
    "StarsTransactionsAPI",
    "StatsAPI",
    "StatsChannelsAPI",
    "StatsGraphAPI",
    "StatsPublicForwardsAPI",
    "StickerEmojiAPI",
    "StickerFavoritesAPI",
    "StickerRecentAPI",
    "StickerSearchAPI",
    "StickerSetsAPI",
    "StickersAPI",
    "StoriesAPI",
    "StoriesCapabilitiesAPI",
    "StoriesFeedAPI",
    "TakeoutAPI",
    "TakeoutMediaAPI",
    "TakeoutMessagesAPI",
    "TodosAPI",
    "TopicsAPI",
    "TopicsForumAPI",
    "TranslateAPI",
    "UpdatesAPI",
    "WebAppsAPI",
]
