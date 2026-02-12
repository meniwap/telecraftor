from __future__ import annotations

from pathlib import Path

from telecraft.client.apis import (
    AccountAPI,
    AdminAPI,
    BusinessAPI,
    CallsAPI,
    ChannelsAPI,
    ChatlistsAPI,
    ChatsAPI,
    ContactsAPI,
    DialogsAPI,
    DiscoveryAPI,
    DraftsAPI,
    FoldersAPI,
    GamesAPI,
    GiftsAPI,
    MediaAPI,
    MessagesAPI,
    NotificationsAPI,
    PeersAPI,
    PollsAPI,
    PresenceAPI,
    PrivacyAPI,
    ProfileAPI,
    ReactionsAPI,
    ReportsAPI,
    SavedAPI,
    SearchAPI,
    StarsAPI,
    StatsAPI,
    StickersAPI,
    StoriesAPI,
    TakeoutAPI,
    TodosAPI,
    TopicsAPI,
    TranslateAPI,
    UpdatesAPI,
    WebAppsAPI,
)
from telecraft.client.mtproto import ClientInit, MtprotoClient


class Client:
    """
    Telecraft V2 high-level client facade.

    `raw` exposes the underlying MtprotoClient for low-level operations.
    """

    def __init__(
        self,
        *,
        network: str = "test",
        dc_id: int = 2,
        host: str | None = None,
        port: int = 443,
        framing: str = "intermediate",
        session_path: str | Path | None = None,
        init: ClientInit | None = None,
        raw: MtprotoClient | None = None,
    ) -> None:
        self.raw = (
            raw
            if raw is not None
            else MtprotoClient(
                network=network,
                dc_id=dc_id,
                host=host,
                port=port,
                framing=framing,
                session_path=session_path,
                init=init,
            )
        )
        self.peers = PeersAPI(self.raw)
        self.profile = ProfileAPI(self.raw)
        self.messages = MessagesAPI(self.raw)
        self.search = SearchAPI(self.raw)
        self.drafts = DraftsAPI(self.raw)
        self.reports = ReportsAPI(self.raw)
        self.media = MediaAPI(self.raw)
        self.chats = ChatsAPI(self.raw)
        self.admin = AdminAPI(self.raw)
        self.contacts = ContactsAPI(self.raw)
        self.polls = PollsAPI(self.raw)
        self.folders = FoldersAPI(self.raw)
        self.games = GamesAPI(self.raw)
        self.saved = SavedAPI(self.raw)
        self.stars = StarsAPI(self.raw)
        self.gifts = GiftsAPI(self.raw)
        self.dialogs = DialogsAPI(self.raw)
        self.stickers = StickersAPI(self.raw)
        self.topics = TopicsAPI(self.raw)
        self.reactions = ReactionsAPI(self.raw)
        self.privacy = PrivacyAPI(self.raw)
        self.notifications = NotificationsAPI(self.raw)
        self.business = BusinessAPI(self.raw)
        self.stories = StoriesAPI(self.raw)
        self.chatlists = ChatlistsAPI(self.raw)
        self.channels = ChannelsAPI(self.raw)
        self.stats = StatsAPI(self.raw)
        self.discovery = DiscoveryAPI(self.raw)
        self.account = AccountAPI(self.raw)
        self.calls = CallsAPI(self.raw)
        self.takeout = TakeoutAPI(self.raw)
        self.webapps = WebAppsAPI(self.raw)
        self.todos = TodosAPI(self.raw)
        self.translate = TranslateAPI(self.raw)
        self.presence = PresenceAPI(self.raw)
        self.updates = UpdatesAPI(self.raw)

    @property
    def is_connected(self) -> bool:
        return self.raw.is_connected

    async def connect(self, *, timeout: float = 30.0) -> None:
        await self.raw.connect(timeout=timeout)

    async def close(self) -> None:
        await self.raw.close()

    async def __aenter__(self) -> Client:
        await self.connect()
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        _ = (exc_type, exc, tb)
        await self.close()
