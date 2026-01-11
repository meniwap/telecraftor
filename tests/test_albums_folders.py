"""
Tests for albums and folder features.
"""

import asyncio
import inspect
from typing import Any

import pytest

from telecraft.client.mtproto import ClientInit, MtprotoClient, MtprotoClientError
from telecraft.tl.generated.functions import (
    MessagesGetDialogFilters,
    MessagesSendMultiMedia,
    MessagesUpdateDialogFilter,
    MessagesUpdateDialogFiltersOrder,
    PhotosDeletePhotos,
    PhotosUploadProfilePhoto,
)
from telecraft.tl.generated.types import (
    DialogFilter,
    InputSingleMedia,
)


def _make_connected_client() -> MtprotoClient:
    c = MtprotoClient(network="test", dc_id=2, init=ClientInit(api_id=1, api_hash="x"))
    c._transport = object()  # type: ignore[attr-defined]
    c._sender = object()  # type: ignore[attr-defined]
    c._state = object()  # type: ignore[attr-defined]
    return c


# ========================== Album Tests ==========================


class TestSendAlbum:
    def test_send_album_signature(self) -> None:
        sig = inspect.signature(MtprotoClient.send_album)
        assert "peer" in sig.parameters
        assert "paths" in sig.parameters
        assert "captions" in sig.parameters
        assert "reply_to_msg_id" in sig.parameters
        assert "silent" in sig.parameters

    def test_send_album_rejects_single_file(self) -> None:
        c = _make_connected_client()
        c.entities.user_access_hash[123] = 456

        with pytest.raises(MtprotoClientError, match="at least 2 files"):
            asyncio.run(c.send_album(("user", 123), ["/path/to/single.jpg"]))

    def test_send_album_rejects_too_many_files(self) -> None:
        c = _make_connected_client()
        c.entities.user_access_hash[123] = 456

        paths = [f"/path/to/file{i}.jpg" for i in range(11)]
        with pytest.raises(MtprotoClientError, match="maximum 10 files"):
            asyncio.run(c.send_album(("user", 123), paths))

    def test_send_album_rejects_mismatched_captions(self) -> None:
        c = _make_connected_client()
        c.entities.user_access_hash[123] = 456

        with pytest.raises(MtprotoClientError, match="captions must match"):
            asyncio.run(
                c.send_album(
                    ("user", 123),
                    ["/path/1.jpg", "/path/2.jpg"],
                    captions=["only one caption"],
                )
            )


class TestSendMultiMediaTL:
    def test_messages_send_multi_media_exists(self) -> None:
        assert MessagesSendMultiMedia.__name__ == "MessagesSendMultiMedia"

    def test_input_single_media_exists(self) -> None:
        assert InputSingleMedia.__name__ == "InputSingleMedia"


# ========================== Profile Photo Tests ==========================


class TestUploadProfilePhoto:
    def test_upload_profile_photo_signature(self) -> None:
        sig = inspect.signature(MtprotoClient.upload_profile_photo)
        assert "path" in sig.parameters
        assert "fallback" in sig.parameters

    def test_upload_profile_photo_rejects_nonexistent_file(self) -> None:
        c = _make_connected_client()

        with pytest.raises(MtprotoClientError, match="not a file"):
            asyncio.run(c.upload_profile_photo("/nonexistent/photo.jpg"))


class TestDeleteProfilePhotos:
    def test_delete_profile_photos_signature(self) -> None:
        sig = inspect.signature(MtprotoClient.delete_profile_photos)
        assert "photo_ids" in sig.parameters

    def test_delete_profile_photos_accepts_single_tuple(self) -> None:
        c = _make_connected_client()
        seen: list[Any] = []

        async def invoke_api(req: Any, *, timeout: float = 0) -> Any:
            seen.append(req)
            return [123]

        c.invoke_api = invoke_api  # type: ignore[assignment]

        result = asyncio.run(c.delete_profile_photos((123, 456)))
        assert result == [123]
        assert len(seen) == 1
        req = seen[0]
        assert getattr(req, "TL_NAME", None) == "photos.deletePhotos"
        assert len(req.id) == 1

    def test_delete_profile_photos_accepts_list(self) -> None:
        c = _make_connected_client()
        seen: list[Any] = []

        async def invoke_api(req: Any, *, timeout: float = 0) -> Any:
            seen.append(req)
            return [123, 456]

        c.invoke_api = invoke_api  # type: ignore[assignment]

        result = asyncio.run(c.delete_profile_photos([(123, 111), (456, 222)]))
        assert result == [123, 456]
        assert len(seen[0].id) == 2


class TestProfilePhotoTL:
    def test_photos_upload_profile_photo_exists(self) -> None:
        assert PhotosUploadProfilePhoto.__name__ == "PhotosUploadProfilePhoto"

    def test_photos_delete_photos_exists(self) -> None:
        assert PhotosDeletePhotos.__name__ == "PhotosDeletePhotos"


# ========================== Folder Tests ==========================


class TestGetFolders:
    def test_get_folders_signature(self) -> None:
        sig = inspect.signature(MtprotoClient.get_folders)
        assert "timeout" in sig.parameters

    def test_get_folders_calls_correct_tl(self) -> None:
        c = _make_connected_client()
        seen: list[Any] = []

        async def invoke_api(req: Any, *, timeout: float = 0) -> Any:
            seen.append(req)
            return type("_F", (), {"filters": []})()

        c.invoke_api = invoke_api  # type: ignore[assignment]

        result = asyncio.run(c.get_folders())
        assert result == []
        assert len(seen) == 1
        assert getattr(seen[0], "TL_NAME", None) == "messages.getDialogFilters"


class TestCreateFolder:
    def test_create_folder_signature(self) -> None:
        sig = inspect.signature(MtprotoClient.create_folder)
        assert "title" in sig.parameters
        assert "folder_id" in sig.parameters
        assert "emoticon" in sig.parameters
        assert "contacts" in sig.parameters
        assert "groups" in sig.parameters
        assert "channels" in sig.parameters

    def test_create_folder_calls_update_dialog_filter(self) -> None:
        c = _make_connected_client()
        seen: list[Any] = []

        async def invoke_api(req: Any, *, timeout: float = 0) -> Any:
            seen.append(req)
            return True

        c.invoke_api = invoke_api  # type: ignore[assignment]

        result = asyncio.run(c.create_folder("My Folder", folder_id=10, groups=True))
        assert result is True
        assert len(seen) == 1
        req = seen[0]
        assert getattr(req, "TL_NAME", None) == "messages.updateDialogFilter"
        assert req.id == 10
        assert req.filter is not None
        assert req.filter.title.text == "My Folder"


class TestDeleteFolder:
    def test_delete_folder_signature(self) -> None:
        sig = inspect.signature(MtprotoClient.delete_folder)
        assert "folder_id" in sig.parameters

    def test_delete_folder_calls_update_with_none_filter(self) -> None:
        c = _make_connected_client()
        seen: list[Any] = []

        async def invoke_api(req: Any, *, timeout: float = 0) -> Any:
            seen.append(req)
            return True

        c.invoke_api = invoke_api  # type: ignore[assignment]

        result = asyncio.run(c.delete_folder(10))
        assert result is True
        assert len(seen) == 1
        req = seen[0]
        assert getattr(req, "TL_NAME", None) == "messages.updateDialogFilter"
        assert req.id == 10
        assert req.filter is None


class TestReorderFolders:
    def test_reorder_folders_signature(self) -> None:
        sig = inspect.signature(MtprotoClient.reorder_folders)
        assert "folder_ids" in sig.parameters

    def test_reorder_folders_calls_correct_tl(self) -> None:
        c = _make_connected_client()
        seen: list[Any] = []

        async def invoke_api(req: Any, *, timeout: float = 0) -> Any:
            seen.append(req)
            return True

        c.invoke_api = invoke_api  # type: ignore[assignment]

        result = asyncio.run(c.reorder_folders([1, 2, 3]))
        assert result is True
        assert len(seen) == 1
        req = seen[0]
        assert getattr(req, "TL_NAME", None) == "messages.updateDialogFiltersOrder"
        assert req.order == [1, 2, 3]


class TestFolderTL:
    def test_messages_get_dialog_filters_exists(self) -> None:
        assert MessagesGetDialogFilters.__name__ == "MessagesGetDialogFilters"

    def test_messages_update_dialog_filter_exists(self) -> None:
        assert MessagesUpdateDialogFilter.__name__ == "MessagesUpdateDialogFilter"

    def test_messages_update_dialog_filters_order_exists(self) -> None:
        assert MessagesUpdateDialogFiltersOrder.__name__ == "MessagesUpdateDialogFiltersOrder"

    def test_dialog_filter_exists(self) -> None:
        assert DialogFilter.__name__ == "DialogFilter"
