from __future__ import annotations

import ast
import importlib.util
import inspect
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from telecraft.client.apis import (
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
    AdminAPI,
    AuthAPI,
    BotsAPI,
    BusinessAPI,
    BusinessLinksAPI,
    BusinessProfileAPI,
    BusinessQuickRepliesAPI,
    CallsAPI,
    CallsConferenceAPI,
    CallsGroupAPI,
    CallsGroupChainAPI,
    CallsStreamAPI,
    ChannelsAPI,
    ChannelsSearchPostsAPI,
    ChannelSettingsAPI,
    ChatlistInvitesAPI,
    ChatlistsAPI,
    ChatlistSuggestionsAPI,
    ChatlistUpdatesAPI,
    ChatsAPI,
    ContactsAPI,
    ContactsRequirementsAPI,
    DialogsAPI,
    DialogsFiltersAPI,
    DialogsPinnedAPI,
    DialogsUnreadAPI,
    DiscoveryAPI,
    DiscoveryBotsAPI,
    DiscoveryChannelsAPI,
    DiscoverySponsoredAPI,
    DraftsAPI,
    FoldersAPI,
    GamesAPI,
    GameScoresAPI,
    GiftsAPI,
    GiftsCollectionsAPI,
    GiftsNotificationsAPI,
    GiftsResaleAPI,
    GiftsSavedAPI,
    GiftsUniqueAPI,
    HelpAPI,
    LangpackAPI,
    MediaAPI,
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
    NotificationsAPI,
    NotificationsContactSignupAPI,
    NotificationsReactionsAPI,
    PaymentsAPI,
    PaymentsFormsAPI,
    PaymentsGiftCodesAPI,
    PaymentsInvoiceAPI,
    PaymentsStarsAPI,
    PeersAPI,
    PollsAPI,
    PresenceAPI,
    PrivacyAPI,
    PrivacyGlobalSettingsAPI,
    ProfileAPI,
    PremiumAPI,
    PremiumBoostsAPI,
    ReactionsAPI,
    ReactionsChatAPI,
    ReactionsDefaultsAPI,
    ReportsAPI,
    SavedAPI,
    SavedDialogsAPI,
    SavedGifsAPI,
    SavedHistoryAPI,
    SavedPinnedAPI,
    SavedReactionTagsAPI,
    SearchAPI,
    StarsAPI,
    StarsFormsAPI,
    StarsRevenueAPI,
    StarsTransactionsAPI,
    StatsAPI,
    StatsChannelsAPI,
    StatsGraphAPI,
    StatsPublicForwardsAPI,
    StickerEmojiAPI,
    StickerFavoritesAPI,
    StickerRecentAPI,
    StickersAPI,
    StickerSearchAPI,
    StickerSetsAPI,
    StoriesAlbumsAPI,
    StoriesAPI,
    StoriesCapabilitiesAPI,
    StoriesFeedAPI,
    StoriesLinksAPI,
    StoriesPeersAPI,
    StoriesReactionsAPI,
    StoriesStealthAPI,
    StoriesViewsAPI,
    TakeoutAPI,
    TakeoutMediaAPI,
    TakeoutMessagesAPI,
    TodosAPI,
    TopicsAPI,
    TopicsForumAPI,
    TranslateAPI,
    UploadsAPI,
    UpdatesAPI,
    UsersAPI,
    WebAppsAPI,
)
from telecraft.client.apis.chats import ChatInvitesAPI, ChatMembersAPI
from telecraft.client.client import Client

MATRIX_PATH = Path("tests/meta/v2_method_matrix.yaml")
ALLOWED_STABILITY = {"experimental", "stable"}
ALLOWED_TIER = {"unit", "live_core", "live_second_account", "live_optional"}
SCENARIOS_STABLE_UNIT_MIN = {
    "delegates_to_raw",
    "forwards_args",
    "returns_expected_shape",
    "handles_rpc_error",
}
SCENARIOS_STABLE_SECOND_ACCOUNT_MIN = SCENARIOS_STABLE_UNIT_MIN | {
    "roundtrip_live",
    "cleanup_on_failure",
}
TEST_DIRS_FOR_NAMING = (
    Path("tests/unit/client/v2"),
    Path("tests/live/core"),
    Path("tests/live/second_account"),
    Path("tests/live/optional"),
)
NAME_RE = re.compile(r"^test_[a-z0-9_]+__[a-z0-9_]+__[a-z0-9_]+$")


@dataclass(frozen=True)
class MethodRef:
    namespace: str
    method: str


def _normalize_token(token: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", token.lower()).strip("_")


def _scenario_test_name(namespace: str, method: str, scenario: str) -> str:
    ns = _normalize_token(namespace)
    meth = _normalize_token(method)
    scen = _normalize_token(scenario)
    return f"test_{ns}__{meth}__{scen}"


def _discover_v2_methods() -> set[MethodRef]:
    refs: set[MethodRef] = set()

    for name, fn in inspect.getmembers(Client, inspect.iscoroutinefunction):
        if not name.startswith("_"):
            refs.add(MethodRef(namespace="client", method=name))

    classes = (
        ("account", AccountAPI),
        ("account.sessions", AccountSessionsAPI),
        ("account.web_sessions", AccountWebSessionsAPI),
        ("account.content", AccountContentAPI),
        ("account.ttl", AccountTTLAPI),
        ("account.terms", AccountTermsAPI),
        ("account.themes", AccountThemesAPI),
        ("account.wallpapers", AccountWallpapersAPI),
        ("account.profile_tab", AccountProfileTabAPI),
        ("account.gift_themes", AccountGiftThemesAPI),
        ("account.music", AccountMusicAPI),
        ("account.music.saved", AccountMusicSavedAPI),
        ("account.paid_messages", AccountPaidMessagesAPI),
        ("account.passkeys", AccountPasskeysAPI),
        ("account.identity", AccountIdentityAPI),
        ("account.personal_channel", AccountPersonalChannelAPI),
        ("admin", AdminAPI),
        ("auth", AuthAPI),
        ("bots", BotsAPI),
        ("chats", ChatsAPI),
        ("chats.members", ChatMembersAPI),
        ("chats.invites", ChatInvitesAPI),
        ("contacts", ContactsAPI),
        ("contacts.requirements", ContactsRequirementsAPI),
        ("search", SearchAPI),
        ("drafts", DraftsAPI),
        ("reports", ReportsAPI),
        ("folders", FoldersAPI),
        ("media", MediaAPI),
        ("messages", MessagesAPI),
        ("messages.scheduled", MessagesScheduledAPI),
        ("messages.web", MessagesWebAPI),
        ("messages.chat_theme", MessagesChatThemeAPI),
        ("messages.suggested_posts", MessagesSuggestedPostsAPI),
        ("messages.fact_checks", MessagesFactChecksAPI),
        ("messages.sponsored", MessagesSponsoredAPI),
        ("messages.saved_tags", MessagesSavedTagsAPI),
        ("messages.attach_menu", MessagesAttachMenuAPI),
        ("messages.discussion", MessagesDiscussionAPI),
        ("messages.receipts", MessagesReceiptsAPI),
        ("messages.effects", MessagesEffectsAPI),
        ("messages.sent_media", MessagesSentMediaAPI),
        ("messages.gifs", MessagesGifsAPI),
        ("messages.paid_reactions", MessagesPaidReactionsAPI),
        ("messages.inline", MessagesInlineAPI),
        ("messages.inline.prepared", MessagesInlinePreparedAPI),
        ("messages.history_import", MessagesHistoryImportAPI),
        ("peers", PeersAPI),
        ("polls", PollsAPI),
        ("presence", PresenceAPI),
        ("profile", ProfileAPI),
        ("dialogs", DialogsAPI),
        ("dialogs.pinned", DialogsPinnedAPI),
        ("dialogs.unread", DialogsUnreadAPI),
        ("dialogs.filters", DialogsFiltersAPI),
        ("stickers", StickersAPI),
        ("stickers.sets", StickerSetsAPI),
        ("stickers.search", StickerSearchAPI),
        ("stickers.recent", StickerRecentAPI),
        ("stickers.favorites", StickerFavoritesAPI),
        ("stickers.emoji", StickerEmojiAPI),
        ("topics", TopicsAPI),
        ("topics.forum", TopicsForumAPI),
        ("reactions", ReactionsAPI),
        ("reactions.defaults", ReactionsDefaultsAPI),
        ("reactions.chat", ReactionsChatAPI),
        ("privacy", PrivacyAPI),
        ("privacy.global_settings", PrivacyGlobalSettingsAPI),
        ("notifications", NotificationsAPI),
        ("notifications.reactions", NotificationsReactionsAPI),
        ("notifications.contact_signup", NotificationsContactSignupAPI),
        ("business", BusinessAPI),
        ("business.links", BusinessLinksAPI),
        ("business.profile", BusinessProfileAPI),
        ("business.quick_replies", BusinessQuickRepliesAPI),
        ("stories", StoriesAPI),
        ("stories.capabilities", StoriesCapabilitiesAPI),
        ("stories.feed", StoriesFeedAPI),
        ("chatlists", ChatlistsAPI),
        ("chatlists.invites", ChatlistInvitesAPI),
        ("chatlists.updates", ChatlistUpdatesAPI),
        ("chatlists.suggestions", ChatlistSuggestionsAPI),
        ("channels", ChannelsAPI),
        ("channels.search_posts", ChannelsSearchPostsAPI),
        ("channels.settings", ChannelSettingsAPI),
        ("stats", StatsAPI),
        ("stats.channels", StatsChannelsAPI),
        ("stats.graph", StatsGraphAPI),
        ("stats.public_forwards", StatsPublicForwardsAPI),
        ("discovery", DiscoveryAPI),
        ("discovery.channels", DiscoveryChannelsAPI),
        ("discovery.bots", DiscoveryBotsAPI),
        ("discovery.sponsored", DiscoverySponsoredAPI),
        ("calls", CallsAPI),
        ("calls.group", CallsGroupAPI),
        ("calls.group.chain", CallsGroupChainAPI),
        ("calls.stream", CallsStreamAPI),
        ("calls.conference", CallsConferenceAPI),
        ("premium", PremiumAPI),
        ("premium.boosts", PremiumBoostsAPI),
        ("takeout", TakeoutAPI),
        ("takeout.messages", TakeoutMessagesAPI),
        ("takeout.media", TakeoutMediaAPI),
        ("webapps", WebAppsAPI),
        ("todos", TodosAPI),
        ("translate", TranslateAPI),
        ("uploads", UploadsAPI),
        ("games", GamesAPI),
        ("games.scores", GameScoresAPI),
        ("saved", SavedAPI),
        ("saved.gifs", SavedGifsAPI),
        ("saved.dialogs", SavedDialogsAPI),
        ("saved.history", SavedHistoryAPI),
        ("saved.reaction_tags", SavedReactionTagsAPI),
        ("saved.pinned", SavedPinnedAPI),
        ("stars", StarsAPI),
        ("stars.transactions", StarsTransactionsAPI),
        ("stars.revenue", StarsRevenueAPI),
        ("stars.forms", StarsFormsAPI),
        ("gifts", GiftsAPI),
        ("gifts.saved", GiftsSavedAPI),
        ("gifts.resale", GiftsResaleAPI),
        ("gifts.unique", GiftsUniqueAPI),
        ("gifts.notifications", GiftsNotificationsAPI),
        ("gifts.collections", GiftsCollectionsAPI),
        ("help", HelpAPI),
        ("langpack", LangpackAPI),
        ("payments", PaymentsAPI),
        ("payments.forms", PaymentsFormsAPI),
        ("payments.invoice", PaymentsInvoiceAPI),
        ("payments.gift_codes", PaymentsGiftCodesAPI),
        ("payments.stars", PaymentsStarsAPI),
        ("updates", UpdatesAPI),
        ("users", UsersAPI),
        ("stories.links", StoriesLinksAPI),
        ("stories.views", StoriesViewsAPI),
        ("stories.reactions", StoriesReactionsAPI),
        ("stories.stealth", StoriesStealthAPI),
        ("stories.peers", StoriesPeersAPI),
        ("stories.albums", StoriesAlbumsAPI),
    )

    for namespace, cls in classes:
        for name, fn in inspect.getmembers(cls, inspect.iscoroutinefunction):
            if not name.startswith("_"):
                refs.add(MethodRef(namespace=namespace, method=name))

    return refs


def _discover_timeout_support() -> dict[MethodRef, bool]:
    timeout_support: dict[MethodRef, bool] = {}

    for name, fn in inspect.getmembers(Client, inspect.iscoroutinefunction):
        if name.startswith("_"):
            continue
        sig = inspect.signature(fn)
        timeout_support[MethodRef(namespace="client", method=name)] = "timeout" in sig.parameters

    classes = (
        ("account", AccountAPI),
        ("account.sessions", AccountSessionsAPI),
        ("account.web_sessions", AccountWebSessionsAPI),
        ("account.content", AccountContentAPI),
        ("account.ttl", AccountTTLAPI),
        ("account.terms", AccountTermsAPI),
        ("account.themes", AccountThemesAPI),
        ("account.wallpapers", AccountWallpapersAPI),
        ("account.profile_tab", AccountProfileTabAPI),
        ("account.gift_themes", AccountGiftThemesAPI),
        ("account.music", AccountMusicAPI),
        ("account.music.saved", AccountMusicSavedAPI),
        ("account.paid_messages", AccountPaidMessagesAPI),
        ("account.passkeys", AccountPasskeysAPI),
        ("account.identity", AccountIdentityAPI),
        ("account.personal_channel", AccountPersonalChannelAPI),
        ("admin", AdminAPI),
        ("auth", AuthAPI),
        ("bots", BotsAPI),
        ("chats", ChatsAPI),
        ("chats.members", ChatMembersAPI),
        ("chats.invites", ChatInvitesAPI),
        ("contacts", ContactsAPI),
        ("contacts.requirements", ContactsRequirementsAPI),
        ("search", SearchAPI),
        ("drafts", DraftsAPI),
        ("reports", ReportsAPI),
        ("folders", FoldersAPI),
        ("media", MediaAPI),
        ("messages", MessagesAPI),
        ("messages.scheduled", MessagesScheduledAPI),
        ("messages.web", MessagesWebAPI),
        ("messages.chat_theme", MessagesChatThemeAPI),
        ("messages.suggested_posts", MessagesSuggestedPostsAPI),
        ("messages.fact_checks", MessagesFactChecksAPI),
        ("messages.sponsored", MessagesSponsoredAPI),
        ("messages.saved_tags", MessagesSavedTagsAPI),
        ("messages.attach_menu", MessagesAttachMenuAPI),
        ("messages.discussion", MessagesDiscussionAPI),
        ("messages.receipts", MessagesReceiptsAPI),
        ("messages.effects", MessagesEffectsAPI),
        ("messages.sent_media", MessagesSentMediaAPI),
        ("messages.gifs", MessagesGifsAPI),
        ("messages.paid_reactions", MessagesPaidReactionsAPI),
        ("messages.inline", MessagesInlineAPI),
        ("messages.inline.prepared", MessagesInlinePreparedAPI),
        ("messages.history_import", MessagesHistoryImportAPI),
        ("peers", PeersAPI),
        ("polls", PollsAPI),
        ("presence", PresenceAPI),
        ("profile", ProfileAPI),
        ("dialogs", DialogsAPI),
        ("dialogs.pinned", DialogsPinnedAPI),
        ("dialogs.unread", DialogsUnreadAPI),
        ("dialogs.filters", DialogsFiltersAPI),
        ("stickers", StickersAPI),
        ("stickers.sets", StickerSetsAPI),
        ("stickers.search", StickerSearchAPI),
        ("stickers.recent", StickerRecentAPI),
        ("stickers.favorites", StickerFavoritesAPI),
        ("stickers.emoji", StickerEmojiAPI),
        ("topics", TopicsAPI),
        ("topics.forum", TopicsForumAPI),
        ("reactions", ReactionsAPI),
        ("reactions.defaults", ReactionsDefaultsAPI),
        ("reactions.chat", ReactionsChatAPI),
        ("privacy", PrivacyAPI),
        ("privacy.global_settings", PrivacyGlobalSettingsAPI),
        ("notifications", NotificationsAPI),
        ("notifications.reactions", NotificationsReactionsAPI),
        ("notifications.contact_signup", NotificationsContactSignupAPI),
        ("business", BusinessAPI),
        ("business.links", BusinessLinksAPI),
        ("business.profile", BusinessProfileAPI),
        ("business.quick_replies", BusinessQuickRepliesAPI),
        ("stories", StoriesAPI),
        ("stories.capabilities", StoriesCapabilitiesAPI),
        ("stories.feed", StoriesFeedAPI),
        ("chatlists", ChatlistsAPI),
        ("chatlists.invites", ChatlistInvitesAPI),
        ("chatlists.updates", ChatlistUpdatesAPI),
        ("chatlists.suggestions", ChatlistSuggestionsAPI),
        ("channels", ChannelsAPI),
        ("channels.search_posts", ChannelsSearchPostsAPI),
        ("channels.settings", ChannelSettingsAPI),
        ("stats", StatsAPI),
        ("stats.channels", StatsChannelsAPI),
        ("stats.graph", StatsGraphAPI),
        ("stats.public_forwards", StatsPublicForwardsAPI),
        ("discovery", DiscoveryAPI),
        ("discovery.channels", DiscoveryChannelsAPI),
        ("discovery.bots", DiscoveryBotsAPI),
        ("discovery.sponsored", DiscoverySponsoredAPI),
        ("calls", CallsAPI),
        ("calls.group", CallsGroupAPI),
        ("calls.group.chain", CallsGroupChainAPI),
        ("calls.stream", CallsStreamAPI),
        ("calls.conference", CallsConferenceAPI),
        ("premium", PremiumAPI),
        ("premium.boosts", PremiumBoostsAPI),
        ("takeout", TakeoutAPI),
        ("takeout.messages", TakeoutMessagesAPI),
        ("takeout.media", TakeoutMediaAPI),
        ("webapps", WebAppsAPI),
        ("todos", TodosAPI),
        ("translate", TranslateAPI),
        ("uploads", UploadsAPI),
        ("games", GamesAPI),
        ("games.scores", GameScoresAPI),
        ("saved", SavedAPI),
        ("saved.gifs", SavedGifsAPI),
        ("saved.dialogs", SavedDialogsAPI),
        ("saved.history", SavedHistoryAPI),
        ("saved.reaction_tags", SavedReactionTagsAPI),
        ("saved.pinned", SavedPinnedAPI),
        ("stars", StarsAPI),
        ("stars.transactions", StarsTransactionsAPI),
        ("stars.revenue", StarsRevenueAPI),
        ("stars.forms", StarsFormsAPI),
        ("gifts", GiftsAPI),
        ("gifts.saved", GiftsSavedAPI),
        ("gifts.resale", GiftsResaleAPI),
        ("gifts.unique", GiftsUniqueAPI),
        ("gifts.notifications", GiftsNotificationsAPI),
        ("gifts.collections", GiftsCollectionsAPI),
        ("help", HelpAPI),
        ("langpack", LangpackAPI),
        ("payments", PaymentsAPI),
        ("payments.forms", PaymentsFormsAPI),
        ("payments.invoice", PaymentsInvoiceAPI),
        ("payments.gift_codes", PaymentsGiftCodesAPI),
        ("payments.stars", PaymentsStarsAPI),
        ("updates", UpdatesAPI),
        ("users", UsersAPI),
        ("stories.links", StoriesLinksAPI),
        ("stories.views", StoriesViewsAPI),
        ("stories.reactions", StoriesReactionsAPI),
        ("stories.stealth", StoriesStealthAPI),
        ("stories.peers", StoriesPeersAPI),
        ("stories.albums", StoriesAlbumsAPI),
    )

    for namespace, cls in classes:
        for name, fn in inspect.getmembers(cls, inspect.iscoroutinefunction):
            if name.startswith("_"):
                continue
            sig = inspect.signature(fn)
            timeout_support[MethodRef(namespace=namespace, method=name)] = (
                "timeout" in sig.parameters
            )

    return timeout_support


def _load_matrix() -> list[dict[str, Any]]:
    raw = MATRIX_PATH.read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, list):
        raise AssertionError("v2_method_matrix.yaml must contain a top-level list")
    return data


def _load_module_from_path(path: Path) -> Any:
    module_name = "telecraft_test_" + re.sub(r"[^a-zA-Z0-9]+", "_", str(path))
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Unable to load test module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _discover_test_function_names() -> set[str]:
    names: set[str] = set()
    for test_dir in TEST_DIRS_FOR_NAMING:
        if not test_dir.exists():
            continue
        for path in sorted(test_dir.rglob("test_*.py")):
            if path.name == "test_v2_wrapper_contracts.py":
                module = _load_module_from_path(path)
                for name, obj in inspect.getmembers(module):
                    if not name.startswith("test_"):
                        continue
                    if inspect.isfunction(obj) or inspect.iscoroutinefunction(obj):
                        names.add(name)
                continue

            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in tree.body:
                if isinstance(
                    node, (ast.FunctionDef, ast.AsyncFunctionDef)
                ) and node.name.startswith("test_"):
                    names.add(node.name)
    return names


def test_v2_method_matrix_is_complete_and_valid() -> None:
    methods = _discover_v2_methods()
    timeout_support = _discover_timeout_support()
    matrix = _load_matrix()

    seen: set[MethodRef] = set()
    for row in matrix:
        namespace = row.get("namespace")
        method = row.get("method")
        stability = row.get("stability")
        tier = row.get("tier")
        required_scenarios = row.get("required_scenarios")

        assert isinstance(namespace, str) and namespace
        assert isinstance(method, str) and method
        assert stability in ALLOWED_STABILITY
        assert tier in ALLOWED_TIER
        assert isinstance(required_scenarios, list) and required_scenarios
        assert all(isinstance(x, str) and x for x in required_scenarios)

        ref = MethodRef(namespace=namespace, method=method)
        assert ref not in seen, f"Duplicate matrix row: {namespace}.{method}"
        seen.add(ref)

        if stability == "stable" and tier == "live_second_account":
            expected = set(SCENARIOS_STABLE_SECOND_ACCOUNT_MIN)
            if timeout_support.get(ref, False):
                expected.add("passes_timeout")
            assert expected.issubset(set(required_scenarios)), (
                f"{namespace}.{method} must include second-account stable minimum scenarios"
            )
        elif stability == "stable":
            expected = set(SCENARIOS_STABLE_UNIT_MIN)
            if timeout_support.get(ref, False):
                expected.add("passes_timeout")
            assert expected.issubset(set(required_scenarios)), (
                f"{namespace}.{method} must include stable minimum scenarios"
            )

    missing = sorted(methods - seen, key=lambda x: (x.namespace, x.method))
    extra = sorted(seen - methods, key=lambda x: (x.namespace, x.method))
    assert not missing, f"Missing matrix entries: {[f'{m.namespace}.{m.method}' for m in missing]}"
    assert not extra, (
        f"Matrix has non-existing methods: {[f'{m.namespace}.{m.method}' for m in extra]}"
    )


def test_v2_required_scenarios_have_named_tests() -> None:
    matrix = _load_matrix()
    discovered_names = _discover_test_function_names()

    missing: list[str] = []
    for row in matrix:
        namespace = str(row["namespace"])
        method = str(row["method"])
        for scenario in row["required_scenarios"]:
            expected = _scenario_test_name(namespace, method, str(scenario))
            if expected not in discovered_names:
                missing.append(expected)

    assert not missing, "Missing required scenario tests (name-based coverage gate):\n" + "\n".join(
        f"- {name}" for name in sorted(missing)
    )


def test_v2_test_names_follow_convention() -> None:
    violations: list[str] = []
    for name in sorted(_discover_test_function_names()):
        if not NAME_RE.match(name):
            violations.append(name)

    assert not violations, (
        "Test name convention violations. Expected: test_<namespace>__<method>__<scenario>\n"
        + "\n".join(f"- {v}" for v in violations)
    )
