from __future__ import annotations

import pytest

from telecraft.client import Client


class _Raw:
    pass


@pytest.mark.unit
def test_folders_extended__assignments__available() -> None:
    client = Client(raw=_Raw())
    assert hasattr(client.folders, "assign")
    assert hasattr(client.folders, "assign_many")
    assert hasattr(client.folders, "archive_many")
    assert hasattr(client.folders, "unarchive_many")
