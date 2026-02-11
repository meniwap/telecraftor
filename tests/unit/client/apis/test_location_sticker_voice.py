"""
Tests for location, stickers, voice, and video note features.
"""

import asyncio
import inspect
from typing import Any

import pytest

from telecraft.client.mtproto import ClientInit, MtprotoClient, MtprotoClientError
from telecraft.tl.generated.functions import (
    MessagesGetStickerSet,
)
from telecraft.tl.generated.types import (
    DocumentAttributeAudio,
    DocumentAttributeVideo,
    InputGeoPoint,
    InputGeoPointEmpty,
    InputMediaContact,
    InputMediaGeoLive,
    InputMediaGeoPoint,
    InputStickerSetShortName,
)


def _make_connected_client() -> MtprotoClient:
    c = MtprotoClient(network="test", dc_id=2, init=ClientInit(api_id=1, api_hash="x"))
    c._transport = object()  # type: ignore[attr-defined]
    c._sender = object()  # type: ignore[attr-defined]
    c._state = object()  # type: ignore[attr-defined]
    return c


# ========================== Location Tests ==========================


class TestSendLocation:
    def test_send_location_signature(self) -> None:
        sig = inspect.signature(MtprotoClient.send_location)
        assert "peer" in sig.parameters
        assert "latitude" in sig.parameters
        assert "longitude" in sig.parameters
        assert "accuracy_radius" in sig.parameters
        assert "reply_to_msg_id" in sig.parameters
        assert "silent" in sig.parameters

    def test_send_location_creates_input_media_geo_point(self) -> None:
        c = _make_connected_client()
        c.entities.user_access_hash[123] = 456
        seen: list[Any] = []

        async def invoke_api(req: Any, *, timeout: float = 0) -> Any:
            seen.append(req)
            return type("_R", (), {"users": [], "chats": []})()

        c.invoke_api = invoke_api  # type: ignore[assignment]

        asyncio.run(c.send_location(("user", 123), 32.0853, 34.7818))

        assert len(seen) == 1
        req = seen[0]
        assert getattr(req, "TL_NAME", None) == "messages.sendMedia"
        assert getattr(req.media, "TL_NAME", None) == "inputMediaGeoPoint"
        geo = req.media.geo_point
        assert getattr(geo, "lat", None) == 32.0853
        assert getattr(geo, "long", None) == 34.7818


class TestSendLiveLocation:
    def test_send_live_location_signature(self) -> None:
        sig = inspect.signature(MtprotoClient.send_live_location)
        assert "peer" in sig.parameters
        assert "latitude" in sig.parameters
        assert "longitude" in sig.parameters
        assert "period" in sig.parameters
        assert "heading" in sig.parameters
        assert "proximity_notification_radius" in sig.parameters

    def test_send_live_location_creates_input_media_geo_live(self) -> None:
        c = _make_connected_client()
        c.entities.user_access_hash[123] = 456
        seen: list[Any] = []

        async def invoke_api(req: Any, *, timeout: float = 0) -> Any:
            seen.append(req)
            return type("_R", (), {"users": [], "chats": []})()

        c.invoke_api = invoke_api  # type: ignore[assignment]

        asyncio.run(
            c.send_live_location(
                ("user", 123),
                32.0853,
                34.7818,
                period=1800,
                heading=90,
            )
        )

        assert len(seen) == 1
        req = seen[0]
        assert getattr(req, "TL_NAME", None) == "messages.sendMedia"
        assert getattr(req.media, "TL_NAME", None) == "inputMediaGeoLive"
        assert req.media.period == 1800
        assert req.media.heading == 90


class TestStopLiveLocation:
    def test_stop_live_location_signature(self) -> None:
        sig = inspect.signature(MtprotoClient.stop_live_location)
        assert "peer" in sig.parameters
        assert "msg_id" in sig.parameters

    def test_stop_live_location_calls_edit_message(self) -> None:
        c = _make_connected_client()
        c.entities.user_access_hash[123] = 456
        seen: list[Any] = []

        async def invoke_api(req: Any, *, timeout: float = 0) -> Any:
            seen.append(req)
            return type("_R", (), {"users": [], "chats": []})()

        c.invoke_api = invoke_api  # type: ignore[assignment]

        asyncio.run(c.stop_live_location(("user", 123), msg_id=100))

        assert len(seen) == 1
        req = seen[0]
        assert getattr(req, "TL_NAME", None) == "messages.editMessage"
        assert req.id == 100
        assert getattr(req.media, "TL_NAME", None) == "inputMediaGeoLive"
        assert req.media.stopped is True


# ========================== Contact Tests ==========================


class TestSendContact:
    def test_send_contact_signature(self) -> None:
        sig = inspect.signature(MtprotoClient.send_contact)
        assert "peer" in sig.parameters
        assert "phone_number" in sig.parameters
        assert "first_name" in sig.parameters
        assert "last_name" in sig.parameters
        assert "vcard" in sig.parameters

    def test_send_contact_creates_input_media_contact(self) -> None:
        c = _make_connected_client()
        c.entities.user_access_hash[123] = 456
        seen: list[Any] = []

        async def invoke_api(req: Any, *, timeout: float = 0) -> Any:
            seen.append(req)
            return type("_R", (), {"users": [], "chats": []})()

        c.invoke_api = invoke_api  # type: ignore[assignment]

        asyncio.run(
            c.send_contact(
                ("user", 123),
                phone_number="+1234567890",
                first_name="John",
                last_name="Doe",
            )
        )

        assert len(seen) == 1
        req = seen[0]
        assert getattr(req, "TL_NAME", None) == "messages.sendMedia"
        assert getattr(req.media, "TL_NAME", None) == "inputMediaContact"
        assert req.media.phone_number == "+1234567890"
        assert req.media.first_name == "John"
        assert req.media.last_name == "Doe"


# ========================== Sticker Tests ==========================


class TestGetStickerSet:
    def test_get_sticker_set_signature(self) -> None:
        sig = inspect.signature(MtprotoClient.get_sticker_set)
        assert "short_name" in sig.parameters

    def test_get_sticker_set_calls_correct_tl(self) -> None:
        c = _make_connected_client()
        seen: list[Any] = []

        async def invoke_api(req: Any, *, timeout: float = 0) -> Any:
            seen.append(req)
            return type("_S", (), {"set": None, "documents": []})()

        c.invoke_api = invoke_api  # type: ignore[assignment]

        asyncio.run(c.get_sticker_set("Animals"))

        assert len(seen) == 1
        req = seen[0]
        assert getattr(req, "TL_NAME", None) == "messages.getStickerSet"
        assert getattr(req.stickerset, "TL_NAME", None) == "inputStickerSetShortName"
        assert req.stickerset.short_name == "Animals"


class TestSendSticker:
    def test_send_sticker_signature(self) -> None:
        sig = inspect.signature(MtprotoClient.send_sticker)
        assert "peer" in sig.parameters
        assert "sticker_id" in sig.parameters
        assert "sticker_access_hash" in sig.parameters
        assert "sticker_file_reference" in sig.parameters

    def test_send_sticker_creates_input_media_document(self) -> None:
        c = _make_connected_client()
        c.entities.user_access_hash[123] = 456
        seen: list[Any] = []

        async def invoke_api(req: Any, *, timeout: float = 0) -> Any:
            seen.append(req)
            return type("_R", (), {"users": [], "chats": []})()

        c.invoke_api = invoke_api  # type: ignore[assignment]

        asyncio.run(
            c.send_sticker(
                ("user", 123),
                sticker_id=111,
                sticker_access_hash=222,
                sticker_file_reference=b"ref",
            )
        )

        assert len(seen) == 1
        req = seen[0]
        assert getattr(req, "TL_NAME", None) == "messages.sendMedia"
        assert getattr(req.media, "TL_NAME", None) == "inputMediaDocument"
        assert req.media.id.id == 111
        assert req.media.id.access_hash == 222


# ========================== Voice Tests ==========================


class TestSendVoice:
    def test_send_voice_signature(self) -> None:
        sig = inspect.signature(MtprotoClient.send_voice)
        assert "peer" in sig.parameters
        assert "path" in sig.parameters
        assert "duration" in sig.parameters
        assert "waveform" in sig.parameters
        assert "caption" in sig.parameters

    def test_send_voice_rejects_nonexistent_file(self) -> None:
        c = _make_connected_client()
        c.entities.user_access_hash[123] = 456

        with pytest.raises(MtprotoClientError, match="not a file"):
            asyncio.run(c.send_voice(("user", 123), "/nonexistent/voice.ogg"))


class TestSendVideoNote:
    def test_send_video_note_signature(self) -> None:
        sig = inspect.signature(MtprotoClient.send_video_note)
        assert "peer" in sig.parameters
        assert "path" in sig.parameters
        assert "duration" in sig.parameters
        assert "length" in sig.parameters
        assert "caption" in sig.parameters

    def test_send_video_note_rejects_nonexistent_file(self) -> None:
        c = _make_connected_client()
        c.entities.user_access_hash[123] = 456

        with pytest.raises(MtprotoClientError, match="not a file"):
            asyncio.run(c.send_video_note(("user", 123), "/nonexistent/video.mp4"))


# ========================== TL Types Existence ==========================


class TestTLTypesExist:
    def test_input_geo_point_exists(self) -> None:
        assert InputGeoPoint.__name__ == "InputGeoPoint"

    def test_input_media_geo_point_exists(self) -> None:
        assert InputMediaGeoPoint.__name__ == "InputMediaGeoPoint"

    def test_input_media_geo_live_exists(self) -> None:
        assert InputMediaGeoLive.__name__ == "InputMediaGeoLive"

    def test_input_geo_point_empty_exists(self) -> None:
        assert InputGeoPointEmpty.__name__ == "InputGeoPointEmpty"

    def test_input_media_contact_exists(self) -> None:
        assert InputMediaContact.__name__ == "InputMediaContact"

    def test_input_sticker_set_short_name_exists(self) -> None:
        assert InputStickerSetShortName.__name__ == "InputStickerSetShortName"

    def test_messages_get_sticker_set_exists(self) -> None:
        assert MessagesGetStickerSet.__name__ == "MessagesGetStickerSet"

    def test_document_attribute_audio_exists(self) -> None:
        assert DocumentAttributeAudio.__name__ == "DocumentAttributeAudio"

    def test_document_attribute_video_exists(self) -> None:
        assert DocumentAttributeVideo.__name__ == "DocumentAttributeVideo"
