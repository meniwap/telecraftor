from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from telecraft import _private_storage


@pytest.mark.skipif(os.name != "posix", reason="POSIX mode assertion")
def test_atomic_write_private_text__creates_target_with_mode_0600(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "session.json"

    _private_storage.atomic_write_private_text(target, "secret\n")

    assert target.read_text(encoding="utf-8") == "secret\n"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


@pytest.mark.skipif(os.name != "posix", reason="POSIX mode assertion")
def test_ensure_private_file__creates_and_tightens_mode(tmp_path: Path) -> None:
    target = tmp_path / "private.sqlite"
    target.write_bytes(b"")
    target.chmod(0o644)

    assert _private_storage.ensure_private_file(target) == target
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_atomic_write_private_text__fsyncs_parent_after_replace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "session.json"
    synced: list[Path] = []
    monkeypatch.setattr(_private_storage, "fsync_directory", synced.append)

    _private_storage.atomic_write_private_text(target, "secret\n")

    assert synced == [tmp_path]


def test_fsync_directory__ignores_unsupported_directory_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_open(_path: object, _flags: int) -> int:
        raise OSError("directory handles unsupported")

    monkeypatch.setattr(_private_storage.os, "open", fail_open)

    _private_storage.fsync_directory(tmp_path)


def test_fsync_directory__closes_handle_when_fsync_is_unsupported(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed: list[int] = []
    monkeypatch.setattr(_private_storage.os, "open", lambda _path, _flags: 123)

    def fail_fsync(_fd: int) -> None:
        raise OSError("directory fsync unsupported")

    monkeypatch.setattr(_private_storage.os, "fsync", fail_fsync)
    monkeypatch.setattr(_private_storage.os, "close", closed.append)

    _private_storage.fsync_directory(tmp_path)

    assert closed == [123]


def test_atomic_write_private_text__cleans_temp_and_preserves_target_on_replace_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "session.json"
    target.write_text("previous\n", encoding="utf-8")

    def fail_replace(_source: object, _target: object) -> None:
        raise OSError("synthetic replace failure")

    monkeypatch.setattr(_private_storage.os, "replace", fail_replace)

    with pytest.raises(OSError, match="synthetic replace failure"):
        _private_storage.atomic_write_private_text(target, "new secret\n")

    assert target.read_text(encoding="utf-8") == "previous\n"
    assert list(tmp_path.glob("*.tmp")) == []
