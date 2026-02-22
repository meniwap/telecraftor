from __future__ import annotations

from .account import (
    AccountAPI,
    AccountContentAPI,
    AccountGiftThemesAPI,
    AccountIdentityAPI,
    AccountMusicAPI,
    AccountMusicSavedAPI,
    AccountPaidMessagesAPI,
    AccountPasskeysAPI,
    AccountPersonalChannelAPI,
    AccountProfileTabAPI,
    AccountSessionsAPI,
    AccountTermsAPI,
    AccountThemesAPI,
    AccountTTLAPI,
    AccountWallpapersAPI,
    AccountWebSessionsAPI,
)
from .admin import AdminAPI
from .auth import AuthAPI
from .business import BusinessAPI, BusinessLinksAPI, BusinessProfileAPI, BusinessQuickRepliesAPI
from .bots import BotsAPI
from .calls import CallsAPI, CallsConferenceAPI, CallsGroupAPI, CallsGroupChainAPI, CallsStreamAPI
from .channels import (
    ChannelAdminLogAPI,
    ChannelLinksAPI,
    ChannelsAPI,
    ChannelsSearchPostsAPI,
    ChannelSettingsAPI,
)
from .chatlists import ChatlistInvitesAPI, ChatlistsAPI, ChatlistSuggestionsAPI, ChatlistUpdatesAPI
from .chats import ChatsAPI
from .contacts import ContactsAPI, ContactsRequirementsAPI
from .dialogs import DialogsAPI, DialogsFiltersAPI, DialogsPinnedAPI, DialogsUnreadAPI
from .discovery import DiscoveryAPI, DiscoveryBotsAPI, DiscoveryChannelsAPI, DiscoverySponsoredAPI
from .drafts import DraftsAPI
from .folders import FoldersAPI
from .games import GamesAPI, GameScoresAPI
from .gifts import (
    GiftsAPI,
    GiftsCollectionsAPI,
    GiftsNotificationsAPI,
    GiftsResaleAPI,
    GiftsSavedAPI,
    GiftsUniqueAPI,
)
from .help import HelpAPI
from .langpack import LangpackAPI
from .media import MediaAPI
from .messages import (
    MessagesAPI,
    MessagesAttachMenuAPI,
    MessagesChatThemeAPI,
    MessagesDiscussionAPI,
    MessagesEffectsAPI,
    MessagesFactChecksAPI,
    MessagesGifsAPI,
    MessagesHistoryImportAPI,
    MessagesInlineAPI,
    MessagesInlinePreparedAPI,
    MessagesPaidReactionsAPI,
    MessagesReceiptsAPI,
    MessagesSavedTagsAPI,
    MessagesScheduledAPI,
    MessagesSentMediaAPI,
    MessagesSponsoredAPI,
    MessagesSuggestedPostsAPI,
    MessagesWebAPI,
)
from .notifications import (
    NotificationsAPI,
    NotificationsContactSignupAPI,
    NotificationsReactionsAPI,
)
from .payments import (
    PaymentsAPI,
    PaymentsFormsAPI,
    PaymentsGiftCodesAPI,
    PaymentsInvoiceAPI,
    PaymentsStarsAPI,
)
from .peers import PeersAPI
from .polls import PollsAPI
from .presence import PresenceAPI
from .privacy import PrivacyAPI, PrivacyGlobalSettingsAPI
from .profile import ProfileAPI
from .premium import PremiumAPI, PremiumBoostsAPI
from .reactions import ReactionsAPI, ReactionsChatAPI, ReactionsDefaultsAPI
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
from .stories import (
    StoriesAlbumsAPI,
    StoriesAPI,
    StoriesCapabilitiesAPI,
    StoriesFeedAPI,
    StoriesLinksAPI,
    StoriesPeersAPI,
    StoriesReactionsAPI,
    StoriesStealthAPI,
    StoriesViewsAPI,
)
from .takeout import TakeoutAPI, TakeoutMediaAPI, TakeoutMessagesAPI
from .todos import TodosAPI
from .topics import TopicsAPI, TopicsForumAPI
from .translate import TranslateAPI
from .uploads import UploadsAPI
from .updates import UpdatesAPI
from .users import UsersAPI
from .webapps import WebAppsAPI

__all__ = [
    "AccountAPI",
    "AccountContentAPI",
    "AccountGiftThemesAPI",
    "AccountIdentityAPI",
    "AccountMusicAPI",
    "AccountMusicSavedAPI",
    "AccountPaidMessagesAPI",
    "AccountPasskeysAPI",
    "AccountPersonalChannelAPI",
    "AccountProfileTabAPI",
    "AccountSessionsAPI",
    "AccountTermsAPI",
    "AccountThemesAPI",
    "AccountTTLAPI",
    "AccountWallpapersAPI",
    "AccountWebSessionsAPI",
    "AdminAPI",
    "AuthAPI",
    "BusinessAPI",
    "BusinessLinksAPI",
    "BusinessProfileAPI",
    "BusinessQuickRepliesAPI",
    "BotsAPI",
    "CallsAPI",
    "CallsConferenceAPI",
    "CallsGroupAPI",
    "CallsGroupChainAPI",
    "CallsStreamAPI",
    "ChannelAdminLogAPI",
    "ChannelLinksAPI",
    "ChannelsSearchPostsAPI",
    "ChannelSettingsAPI",
    "ChannelsAPI",
    "ChatlistInvitesAPI",
    "ChatlistSuggestionsAPI",
    "ChatlistUpdatesAPI",
    "ChatlistsAPI",
    "ChatsAPI",
    "ContactsAPI",
    "ContactsRequirementsAPI",
    "DialogsAPI",
    "DialogsFiltersAPI",
    "DialogsPinnedAPI",
    "DialogsUnreadAPI",
    "DiscoveryAPI",
    "DiscoveryBotsAPI",
    "DiscoveryChannelsAPI",
    "DiscoverySponsoredAPI",
    "DraftsAPI",
    "FoldersAPI",
    "GameScoresAPI",
    "GamesAPI",
    "GiftsAPI",
    "GiftsCollectionsAPI",
    "GiftsNotificationsAPI",
    "GiftsResaleAPI",
    "GiftsSavedAPI",
    "GiftsUniqueAPI",
    "HelpAPI",
    "LangpackAPI",
    "MediaAPI",
    "MessagesAPI",
    "MessagesAttachMenuAPI",
    "MessagesChatThemeAPI",
    "MessagesDiscussionAPI",
    "MessagesEffectsAPI",
    "MessagesFactChecksAPI",
    "MessagesGifsAPI",
    "MessagesHistoryImportAPI",
    "MessagesInlineAPI",
    "MessagesInlinePreparedAPI",
    "MessagesPaidReactionsAPI",
    "MessagesReceiptsAPI",
    "MessagesSavedTagsAPI",
    "MessagesScheduledAPI",
    "MessagesSentMediaAPI",
    "MessagesSponsoredAPI",
    "MessagesSuggestedPostsAPI",
    "MessagesWebAPI",
    "NotificationsAPI",
    "NotificationsContactSignupAPI",
    "NotificationsReactionsAPI",
    "PaymentsAPI",
    "PaymentsFormsAPI",
    "PaymentsGiftCodesAPI",
    "PaymentsInvoiceAPI",
    "PaymentsStarsAPI",
    "PeersAPI",
    "PollsAPI",
    "PresenceAPI",
    "PrivacyAPI",
    "PrivacyGlobalSettingsAPI",
    "PremiumAPI",
    "PremiumBoostsAPI",
    "ProfileAPI",
    "ReactionsAPI",
    "ReactionsChatAPI",
    "ReactionsDefaultsAPI",
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
    "StoriesAlbumsAPI",
    "StoriesCapabilitiesAPI",
    "StoriesFeedAPI",
    "StoriesLinksAPI",
    "StoriesPeersAPI",
    "StoriesReactionsAPI",
    "StoriesStealthAPI",
    "StoriesViewsAPI",
    "TakeoutAPI",
    "TakeoutMediaAPI",
    "TakeoutMessagesAPI",
    "TodosAPI",
    "TopicsAPI",
    "TopicsForumAPI",
    "TranslateAPI",
    "UploadsAPI",
    "UpdatesAPI",
    "UsersAPI",
    "WebAppsAPI",
]
