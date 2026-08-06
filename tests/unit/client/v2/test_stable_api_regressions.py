from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from telecraft.client import Client
from telecraft.client.media import MediaError
from telecraft.tl.generated.types import InputMessagesFilterEmpty, InputMessagesFilterPhotos


class _Entities:
    def input_peer(self, resolved: Any) -> Any:
        return {"resolved_peer": resolved}

    def input_user(self, user_id: int) -> Any:
        return {"input_user": int(user_id)}


class _Raw:
    is_connected = False

    def __init__(self, *responses: Any) -> None:
        self.entities = _Entities()
        self.responses = list(responses)
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    async def resolve_peer(self, peer: Any, *, timeout: float = 20.0) -> Any:
        self.calls.append(("resolve_peer", (peer,), {"timeout": timeout}))
        if isinstance(peer, str) and peer.startswith("user:"):
            return SimpleNamespace(peer_type="user", peer_id=int(peer.partition(":")[2]))
        return SimpleNamespace(peer_type="channel", peer_id=123)

    async def invoke_api(self, request: Any, *, timeout: float = 20.0) -> Any:
        self.calls.append(("invoke_api", (request,), {"timeout": timeout}))
        if self.responses:
            return self.responses.pop(0)
        return {"ok": True}

    async def transfer_members(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("transfer_members", args, kwargs))
        return {"success": [], "failed": []}

    async def search_messages(self, *args: Any, **kwargs: Any) -> list[Any]:
        self.calls.append(("search_messages", args, kwargs))
        return []


def _collect_file(client: Client) -> list[bytes]:
    async def collect() -> list[bytes]:
        return [chunk async for chunk in client.uploads.iter_file(object())]

    return asyncio.run(collect())


def test_chats_members__transfer__forwards_optional_policies() -> None:
    raw = _Raw()
    client = Client(raw=raw)  # type: ignore[arg-type]

    asyncio.run(
        client.chats.members.transfer(
            from_group="channel:1",
            to_group="channel:2",
            limit=7,
            exclude_bots=False,
            exclude_self=False,
            on_error="raise",
            timeout=4.5,
        )
    )

    name, _, kwargs = raw.calls[-1]
    assert name == "transfer_members"
    assert kwargs == {
        "from_group": "channel:1",
        "to_group": "channel:2",
        "limit": 7,
        "exclude_bots": False,
        "exclude_self": False,
        "exclude_admins": False,
        "on_error": "raise",
        "timeout": 4.5,
    }


def test_search__sent_media__forwards_filter() -> None:
    raw = _Raw()
    client = Client(raw=raw)  # type: ignore[arg-type]
    media_filter = InputMessagesFilterPhotos()

    result = asyncio.run(
        client.search.sent_media(
            "channel:1",
            q="receipt",
            filter=media_filter,
            offset_id=81,
            limit=17,
            timeout=3.5,
        )
    )

    assert result == []
    name, args, kwargs = raw.calls[-1]
    assert name == "search_messages"
    assert args == ("channel:1",)
    assert kwargs == {
        "query": "receipt",
        "filter": media_filter,
        "offset_id": 81,
        "limit": 17,
        "timeout": 3.5,
    }


@pytest.mark.parametrize(
    ("kwargs", "expected_flags"),
    [
        ({"broadcasts_only": True}, 1 << 1),
        ({"groups_only": True}, 1 << 2),
        ({"users_only": True}, 1 << 3),
        ({"folder_id": 4}, 1),
    ],
)
def test_search__global_messages__uses_protocol_flag_bits(
    kwargs: dict[str, Any], expected_flags: int
) -> None:
    raw = _Raw()
    client = Client(raw=raw)  # type: ignore[arg-type]

    asyncio.run(client.search.global_messages(**kwargs))

    request = raw.calls[-1][1][0]
    assert request.TL_NAME == "messages.searchGlobal"
    assert request.flags == expected_flags
    assert request.community is None


def test_messages_sent_media__search__forwards_optional_args() -> None:
    raw = _Raw()
    client = Client(raw=raw)  # type: ignore[arg-type]
    media_filter = InputMessagesFilterPhotos()

    asyncio.run(
        client.messages.sent_media.search(
            "channel:123",
            q="photo",
            filter=media_filter,
            offset_id=90,
            add_offset=-4,
            limit=11,
            max_id=120,
            min_id=20,
            timeout=6.5,
        )
    )

    resolve_call, invoke_call = raw.calls
    assert resolve_call == ("resolve_peer", ("channel:123",), {"timeout": 6.5})
    assert invoke_call[0] == "invoke_api"
    request = invoke_call[1][0]
    assert request.TL_NAME == "messages.search"
    assert request.peer == {"resolved_peer": SimpleNamespace(peer_type="channel", peer_id=123)}
    assert request.q == "photo"
    assert request.filter is media_filter
    assert request.offset_id == 90
    assert request.add_offset == -4
    assert request.limit == 11
    assert request.max_id == 120
    assert request.min_id == 20
    assert invoke_call[2] == {"timeout": 6.5}


def test_messages_sent_media__search__supports_defaults() -> None:
    raw = _Raw()
    client = Client(raw=raw)  # type: ignore[arg-type]

    asyncio.run(client.messages.sent_media.search("channel:123"))

    request = raw.calls[-1][1][0]
    assert request.TL_NAME == "messages.search"
    assert isinstance(request.filter, InputMessagesFilterEmpty)
    assert request.offset_id == 0
    assert request.add_offset == 0
    assert request.limit == 100
    assert request.max_id == 0
    assert request.min_id == 0


def test_messages_effects__send_text__sets_effect_flag() -> None:
    raw = _Raw()
    client = Client(raw=raw)  # type: ignore[arg-type]

    asyncio.run(
        client.messages.effects.send_text(
            "channel:123",
            "hello",
            77,
            silent=True,
        )
    )

    request = raw.calls[-1][1][0]
    assert request.TL_NAME == "messages.sendMessage"
    assert request.flags == (1 << 18) | (1 << 5)
    assert request.effect == 77
    assert request.rich_message is None


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (SimpleNamespace(TL_NAME="upload.fileCdnRedirect"), "CDN redirect"),
        (SimpleNamespace(TL_NAME="upload.file"), "bytes missing/invalid"),
        (object(), "unexpected upload.getFile result"),
    ],
)
def test_uploads__iter_file__rejects_non_file_results(response: Any, message: str) -> None:
    client = Client(raw=_Raw(response))  # type: ignore[arg-type]

    with pytest.raises(MediaError, match=message):
        _collect_file(client)


def test_uploads__iter_file__yields_valid_chunks() -> None:
    client = Client(raw=_Raw(SimpleNamespace(TL_NAME="upload.file", bytes=b"ok")))  # type: ignore[arg-type]

    assert _collect_file(client) == [b"ok"]


@pytest.mark.parametrize("kwargs", [{"color": 0x112233}, {"intensity": 50}])
def test_account_wallpapers__search__rejects_unsupported_options(kwargs: dict[str, int]) -> None:
    raw = _Raw()
    client = Client(raw=raw)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="does not support color or intensity"):
        asyncio.run(client.account.wallpapers.search("slug", **kwargs))

    assert raw.calls == []


def test_account_wallpapers__search__supports_slug_lookup() -> None:
    raw = _Raw()
    client = Client(raw=raw)  # type: ignore[arg-type]

    asyncio.run(client.account.wallpapers.search("mountains", timeout=7.0))

    name, args, kwargs = raw.calls[-1]
    assert name == "invoke_api"
    request = args[0]
    assert request.TL_NAME == "account.getWallPaper"
    assert request.wallpaper.TL_NAME == "inputWallPaperSlug"
    assert request.wallpaper.slug == "mountains"
    assert kwargs == {"timeout": 7.0}


def test_account_personal_channel__candidates__supports_current_schema() -> None:
    raw = _Raw()
    client = Client(raw=raw)  # type: ignore[arg-type]

    asyncio.run(client.account.personal_channel.candidates())

    request = raw.calls[-1][1][0]
    assert request.TL_NAME == "channels.getAdminedPublicChannels"
    assert request.flags == 1 << 2
    assert request.for_personal is True
    assert request.for_community_peer is None


def test_translate__text__rejects_unsupported_from_lang() -> None:
    raw = _Raw()
    client = Client(raw=raw)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="does not support from_lang"):
        asyncio.run(client.translate.text("shalom", "en", from_lang="he"))

    assert raw.calls == []


def test_translate__text__uses_auto_detection_and_text_flag() -> None:
    raw = _Raw()
    client = Client(raw=raw)  # type: ignore[arg-type]

    asyncio.run(client.translate.text("shalom", "en", timeout=8.0))

    request = raw.calls[-1][1][0]
    assert request.TL_NAME == "messages.translateText"
    assert request.flags == 1 << 1
    assert request.peer is None
    assert request.id is None
    assert request.text[0].TL_NAME == "textWithEntities"
    assert request.text[0].text == "shalom"
    assert request.text[0].entities == []
    assert request.to_lang == "en"


def test_webapps__request__builds_simple_webview_with_input_user() -> None:
    raw = _Raw()
    client = Client(raw=raw)  # type: ignore[arg-type]

    asyncio.run(
        client.webapps.request(
            bot="user:7",
            url="https://example.test/app",
            start_param="start",
            theme_params={"bg_color": "#ffffff"},
            timeout=4.0,
        )
    )

    request = raw.calls[-1][1][0]
    assert request.TL_NAME == "messages.requestSimpleWebView"
    assert request.flags == (1 << 3) | (1 << 4) | 1
    assert request.bot == {"input_user": 7}
    assert request.url == "https://example.test/app"
    assert request.start_param == "start"
    assert request.theme_params.data == '{"bg_color":"#ffffff"}'


def test_webapps__request__honors_peer_with_bound_webview() -> None:
    raw = _Raw()
    client = Client(raw=raw)  # type: ignore[arg-type]

    asyncio.run(
        client.webapps.request(
            peer="channel:123",
            bot="user:7",
            url="https://example.test/app",
            start_param="start",
            theme_params={"bg_color": "#ffffff"},
            timeout=5.0,
        )
    )

    request = raw.calls[-1][1][0]
    assert request.TL_NAME == "messages.requestWebView"
    assert request.flags == (1 << 1) | (1 << 3) | (1 << 2)
    assert request.peer == {"resolved_peer": SimpleNamespace(peer_type="channel", peer_id=123)}
    assert request.bot == {"input_user": 7}
    assert request.url == "https://example.test/app"
    assert request.start_param == "start"
    assert request.theme_params.data == '{"bg_color":"#ffffff"}'


def test_webapps__request_app__uses_input_user_for_short_name() -> None:
    raw = _Raw()
    client = Client(raw=raw)  # type: ignore[arg-type]

    asyncio.run(client.webapps.request_app("user:7", app="catalog"))

    request = raw.calls[-1][1][0]
    assert request.TL_NAME == "messages.requestAppWebView"
    assert request.app.TL_NAME == "inputBotAppShortName"
    assert request.app.bot_id == {"input_user": 7}
    assert request.app.short_name == "catalog"


def test_webapps__prolong__uses_protocol_flag_bits_and_input_user() -> None:
    raw = _Raw()
    client = Client(raw=raw)  # type: ignore[arg-type]

    asyncio.run(
        client.webapps.prolong(
            "channel:123",
            "user:7",
            42,
            reply_to_msg_id=9,
            send_as="user:8",
            silent=True,
        )
    )

    request = raw.calls[-1][1][0]
    assert request.TL_NAME == "messages.prolongWebView"
    assert request.flags == (1 << 5) | 1 | (1 << 13)
    assert request.bot == {"input_user": 7}
    assert request.reply_to.reply_to_msg_id == 9
    assert request.send_as == {"resolved_peer": SimpleNamespace(peer_type="user", peer_id=8)}


def test_webapps__send_data__uses_input_user() -> None:
    raw = _Raw()
    client = Client(raw=raw)  # type: ignore[arg-type]

    asyncio.run(client.webapps.send_data("user:7", "Open", "payload"))

    request = raw.calls[-1][1][0]
    assert request.TL_NAME == "messages.sendWebViewData"
    assert request.bot == {"input_user": 7}


def test_webapps__invoke_custom__uses_input_user() -> None:
    raw = _Raw()
    client = Client(raw=raw)  # type: ignore[arg-type]

    asyncio.run(client.webapps.invoke_custom("user:7", "ping", {"ok": True}))

    request = raw.calls[-1][1][0]
    assert request.TL_NAME == "bots.invokeWebViewCustomMethod"
    assert request.bot == {"input_user": 7}
