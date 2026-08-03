from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from telecraft.client.entities import (
    EntityCache,
    EntityCacheStorageError,
    load_entity_cache_file,
    save_entity_cache_file,
)


def test_entity_cache_storage_roundtrip(tmp_path) -> None:
    p = tmp_path / "x.entities.json"
    cache = EntityCache(auth_key_id="0123456789abcdef", self_user_id=111)
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
    assert got.auth_key_id == cache.auth_key_id
    assert got.self_user_id == cache.self_user_id


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
    assert got.auth_key_id is None


def test_entity_cache_storage_rejects_invalid_auth_key_id(tmp_path) -> None:
    p = tmp_path / "x.entities.json"
    p.write_text(
        json.dumps(
            {
                "version": 3,
                "auth_key_id": "not-hex",
                "user_access_hash": {},
                "channel_access_hash": {},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(EntityCacheStorageError):
        load_entity_cache_file(p)


def test_entity_cache_rejects_context_bound_min_access_hashes() -> None:
    cache = EntityCache(
        user_access_hash={1: 111},
        channel_access_hash={2: 222},
    )
    cache.ingest_users(
        [
            SimpleNamespace(
                TL_NAME="user",
                id=1,
                access_hash=999,
                min=True,
                username="min_user",
                phone="15551234567",
            ),
            SimpleNamespace(
                TL_NAME="user",
                id=3,
                access_hash=777,
                min=True,
                username="new_min_user",
                phone="15557654321",
            ),
        ]
    )
    cache.ingest_chats(
        [
            SimpleNamespace(
                TL_NAME="channel",
                id=2,
                access_hash=888,
                min=True,
                username="min_channel",
            ),
            SimpleNamespace(
                TL_NAME="channel",
                id=4,
                access_hash=666,
                min=True,
                username="new_min_channel",
            ),
        ]
    )

    assert cache.user_access_hash == {1: 111}
    assert cache.channel_access_hash == {2: 222}
    assert "min_user" not in cache.username_to_peer
    assert "min_channel" not in cache.username_to_peer
    assert "new_min_user" not in cache.username_to_peer
    assert "new_min_channel" not in cache.username_to_peer
    assert cache.phone_to_user_id == {}


def test_input_channel_or_none_does_not_raise_on_cache_miss() -> None:
    cache = EntityCache()

    assert cache.input_channel_or_none(123) is None
