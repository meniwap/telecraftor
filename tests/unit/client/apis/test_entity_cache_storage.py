from __future__ import annotations

import json

import pytest

from telecraft.client.entities import (
    EntityCache,
    EntityCacheStorageError,
    load_entity_cache_file,
    save_entity_cache_file,
)


def test_entity_cache_storage_roundtrip(tmp_path) -> None:
    p = tmp_path / "x.entities.json"
    cache = EntityCache()
    cache.user_access_hash[111] = 222
    cache.channel_access_hash[333] = 444
    cache.username_to_peer["alice"] = ("user", 111)
    cache.username_to_peer["mychan"] = ("channel", 333)
    cache.phone_to_user_id["+15551234567"] = 111
    save_entity_cache_file(p, cache)
    got = load_entity_cache_file(p)
    assert got.user_access_hash == cache.user_access_hash
    assert got.channel_access_hash == cache.channel_access_hash
    assert got.username_to_peer == cache.username_to_peer
    assert got.phone_to_user_id == cache.phone_to_user_id


def test_entity_cache_storage_bad_version(tmp_path) -> None:
    p = tmp_path / "x.entities.json"
    p.write_text(
        json.dumps(
            {
                "version": 999,
                "user_access_hash": {"1": 2},
                "channel_access_hash": {"3": 4},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(EntityCacheStorageError):
        _ = load_entity_cache_file(p)


def test_entity_cache_storage_migrates_v1(tmp_path) -> None:
    p = tmp_path / "x.entities.json"
    p.write_text(
        json.dumps(
            {
                "version": 1,
                "user_access_hash": {"1": 2},
                "channel_access_hash": {"3": 4},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    got = load_entity_cache_file(p)
    assert got.user_access_hash == {1: 2}
    assert got.channel_access_hash == {3: 4}
    assert got.username_to_peer == {}
    assert got.phone_to_user_id == {}


