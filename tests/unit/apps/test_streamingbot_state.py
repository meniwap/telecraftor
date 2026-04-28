from __future__ import annotations

from pathlib import Path

from apps.streamingbot.state import OffsetState, OffsetStore


def test_streamingbot_state__load__missing_file_returns_empty_state(tmp_path: Path) -> None:
    store = OffsetStore(tmp_path / "offset.json")
    state = store.load()
    assert state.next_update_id is None


def test_streamingbot_state__save_and_load_roundtrip(tmp_path: Path) -> None:
    store = OffsetStore(tmp_path / "offset.json")
    store.save(OffsetState(next_update_id=123456))
    state = store.load()
    assert state.next_update_id == 123456


def test_streamingbot_state__load__corrupt_json_returns_empty_state(tmp_path: Path) -> None:
    path = tmp_path / "offset.json"
    path.write_text("{bad json", encoding="utf-8")
    store = OffsetStore(path)
    state = store.load()
    assert state.next_update_id is None
