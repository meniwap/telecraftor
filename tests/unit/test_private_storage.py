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
