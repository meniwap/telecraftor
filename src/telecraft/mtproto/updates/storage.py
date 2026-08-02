from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from telecraft._private_storage import atomic_write_private_text
from telecraft.mtproto.updates.state import UpdatesState

_UPDATES_STATE_VERSION = 2


class UpdatesStateStorageError(Exception):
    pass


class LegacyUpdatesStateMigrationRequired(UpdatesStateStorageError):
    """Raised when an unbound v1 checkpoint needs an explicit trust decision."""


@dataclass(slots=True)
class PersistedUpdatesState:
    """
    Persistent representation of UpdatesState.

    Stored separately from the MTProto session so we can evolve it independently.
    """

    pts: int
    qts: int
    date: int
    seq: int
    auth_key_id: str | None = None
    version: int = _UPDATES_STATE_VERSION

    def validate(self) -> None:
        if self.version not in {1, _UPDATES_STATE_VERSION}:
            raise UpdatesStateStorageError(f"Unsupported updates state version: {self.version}")
        for name in ("pts", "qts", "date", "seq"):
            v = getattr(self, name)
            if not isinstance(v, int) or v < 0:
                raise UpdatesStateStorageError(f"Invalid {name}: {v!r}")
        if self.auth_key_id is not None:
            value = self.auth_key_id.casefold()
            if len(value) != 16 or any(char not in "0123456789abcdef" for char in value):
                raise UpdatesStateStorageError("Invalid auth_key_id")
            self.auth_key_id = value

    def to_updates_state(self) -> UpdatesState:
        self.validate()
        return UpdatesState(pts=self.pts, qts=self.qts, date=self.date, seq=self.seq)

    @classmethod
    def from_updates_state(
        cls,
        state: UpdatesState,
        *,
        auth_key_id: str | None = None,
    ) -> PersistedUpdatesState:
        return cls(
            pts=int(state.pts),
            qts=int(state.qts),
            date=int(state.date),
            seq=int(state.seq),
            auth_key_id=auth_key_id,
        )

    def to_json_dict(self) -> dict[str, object]:
        self.validate()
        return {
            "version": int(self.version),
            "auth_key_id": self.auth_key_id,
            "pts": int(self.pts),
            "qts": int(self.qts),
            "date": int(self.date),
            "seq": int(self.seq),
        }

    @classmethod
    def from_json_dict(cls, data: dict[str, object]) -> PersistedUpdatesState:
        try:
            version_obj = data.get("version", _UPDATES_STATE_VERSION)
            if not isinstance(version_obj, (int, str)):
                raise UpdatesStateStorageError("Invalid version")
            version = int(version_obj)
            if version not in {1, _UPDATES_STATE_VERSION}:
                raise UpdatesStateStorageError(f"Unsupported updates state version: {version}")

            auth_key_id: str | None = None
            if version >= 2:
                auth_key_id_obj = data.get("auth_key_id")
                if auth_key_id_obj is not None:
                    if not isinstance(auth_key_id_obj, str):
                        raise UpdatesStateStorageError("Invalid auth_key_id")
                    auth_key_id = auth_key_id_obj

            def _need_int(k: str) -> int:
                v = data[k]
                if not isinstance(v, (int, str)):
                    raise UpdatesStateStorageError(f"Invalid {k}")
                return int(v)

            pts = _need_int("pts")
            qts = _need_int("qts")
            date = _need_int("date")
            seq = _need_int("seq")
        except KeyError as e:
            raise UpdatesStateStorageError(f"Missing field: {e}") from e
        except Exception as e:  # noqa: BLE001
            raise UpdatesStateStorageError("Invalid updates state JSON shape") from e

        out = cls(
            pts=pts,
            qts=qts,
            date=date,
            seq=seq,
            auth_key_id=auth_key_id,
            version=version,
        )
        out.validate()
        return out


def load_updates_state_file(
    path: str | Path,
    *,
    expected_auth_key_id: str | None = None,
    allow_unbound_legacy: bool = False,
) -> UpdatesState:
    p = Path(path)
    raw = p.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except Exception as e:  # noqa: BLE001
        raise UpdatesStateStorageError(f"Failed to parse updates state JSON: {p}") from e
    if not isinstance(data, dict):
        raise UpdatesStateStorageError("Updates state JSON must be an object")
    persisted = PersistedUpdatesState.from_json_dict(data)
    if expected_auth_key_id is not None:
        expected = expected_auth_key_id.casefold()
        unbound_legacy = persisted.version == 1 and persisted.auth_key_id is None
        legacy_migration = allow_unbound_legacy and unbound_legacy
        if unbound_legacy and not legacy_migration:
            raise LegacyUpdatesStateMigrationRequired(
                "Legacy updates state is not bound to an authorization"
            )
        if persisted.auth_key_id != expected and not legacy_migration:
            raise UpdatesStateStorageError("Updates state belongs to a different authorization")
    return persisted.to_updates_state()


def save_updates_state_file(
    path: str | Path,
    state: UpdatesState,
    *,
    auth_key_id: str | None = None,
) -> None:
    payload = PersistedUpdatesState.from_updates_state(state, auth_key_id=auth_key_id)
    atomic_write_private_text(
        path,
        json.dumps(payload.to_json_dict(), indent=2, sort_keys=True) + "\n",
    )
