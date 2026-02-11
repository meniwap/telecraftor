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
    AdminAPI,
    BusinessAPI,
    BusinessLinksAPI,
    BusinessProfileAPI,
    BusinessQuickRepliesAPI,
    ChannelsAPI,
    ChannelSettingsAPI,
    ChatlistInvitesAPI,
    ChatlistsAPI,
    ChatlistSuggestionsAPI,
    ChatlistUpdatesAPI,
    ChatsAPI,
    ContactsAPI,
    DialogsAPI,
    DialogsFiltersAPI,
    DialogsPinnedAPI,
    DialogsUnreadAPI,
    FoldersAPI,
    GamesAPI,
    GameScoresAPI,
    GiftsAPI,
    GiftsResaleAPI,
    GiftsSavedAPI,
    GiftsUniqueAPI,
    MediaAPI,
    MessagesAPI,
    NotificationsAPI,
    NotificationsContactSignupAPI,
    NotificationsReactionsAPI,
    PeersAPI,
    PollsAPI,
    PresenceAPI,
    PrivacyAPI,
    PrivacyGlobalSettingsAPI,
    ProfileAPI,
    ReactionsAPI,
    SavedAPI,
    SavedDialogsAPI,
    SavedGifsAPI,
    SavedHistoryAPI,
    SavedPinnedAPI,
    SavedReactionTagsAPI,
    StarsAPI,
    StarsFormsAPI,
    StarsRevenueAPI,
    StarsTransactionsAPI,
    StickerEmojiAPI,
    StickerFavoritesAPI,
    StickerRecentAPI,
    StickersAPI,
    StickerSearchAPI,
    StickerSetsAPI,
    StoriesAPI,
    StoriesCapabilitiesAPI,
    StoriesFeedAPI,
    TopicsAPI,
    TopicsForumAPI,
    UpdatesAPI,
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
        ("admin", AdminAPI),
        ("chats", ChatsAPI),
        ("chats.members", ChatMembersAPI),
        ("chats.invites", ChatInvitesAPI),
        ("contacts", ContactsAPI),
        ("folders", FoldersAPI),
        ("media", MediaAPI),
        ("messages", MessagesAPI),
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
        ("channels.settings", ChannelSettingsAPI),
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
        ("updates", UpdatesAPI),
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
        ("admin", AdminAPI),
        ("chats", ChatsAPI),
        ("chats.members", ChatMembersAPI),
        ("chats.invites", ChatInvitesAPI),
        ("contacts", ContactsAPI),
        ("folders", FoldersAPI),
        ("media", MediaAPI),
        ("messages", MessagesAPI),
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
        ("channels.settings", ChannelSettingsAPI),
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
        ("updates", UpdatesAPI),
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
