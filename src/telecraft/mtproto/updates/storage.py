from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from telecraft._private_storage import atomic_write_private_text
from telecraft.mtproto.updates.state import UpdatesState

_UPDATES_STATE_VERSION = 3
_SUPPORTED_UPDATES_STATE_VERSIONS = frozenset({1, 2, _UPDATES_STATE_VERSION})


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
    channel_pts: dict[int, int] = field(default_factory=dict)
    version: int = _UPDATES_STATE_VERSION

    def validate(self) -> None:
        if self.version not in _SUPPORTED_UPDATES_STATE_VERSIONS:
            raise UpdatesStateStorageError(f"Unsupported updates state version: {self.version}")
        for name in ("pts", "qts", "date", "seq"):
            v = getattr(self, name)
            if isinstance(v, bool) or not isinstance(v, int) or v < 0:
                raise UpdatesStateStorageError(f"Invalid {name}: {v!r}")
        if not isinstance(self.channel_pts, dict):
            raise UpdatesStateStorageError("Invalid channel_pts")
        if self.version < 3 and self.channel_pts:
            raise UpdatesStateStorageError(
                f"Updates state version {self.version} cannot contain channel_pts"
            )
        for channel_id, pts in self.channel_pts.items():
            if isinstance(channel_id, bool) or not isinstance(channel_id, int) or channel_id <= 0:
                raise UpdatesStateStorageError(f"Invalid channel id: {channel_id!r}")
            if isinstance(pts, bool) or not isinstance(pts, int) or pts < 0:
                raise UpdatesStateStorageError(
                    f"Invalid channel pts for channel {channel_id}: {pts!r}"
                )
        if self.auth_key_id is not None:
            value = self.auth_key_id.casefold()
            if len(value) != 16 or any(char not in "0123456789abcdef" for char in value):
                raise UpdatesStateStorageError("Invalid auth_key_id")
            self.auth_key_id = value

    def to_updates_state(self) -> UpdatesState:
        self.validate()
        return UpdatesState(
            pts=self.pts,
            qts=self.qts,
            date=self.date,
            seq=self.seq,
            channel_pts=dict(self.channel_pts),
        )

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
            channel_pts={
                int(channel_id): int(pts) for channel_id, pts in state.channel_pts.items()
            },
        )

    def to_json_dict(self) -> dict[str, object]:
        self.validate()
        payload: dict[str, object] = {
            "version": int(self.version),
            "auth_key_id": self.auth_key_id,
            "pts": int(self.pts),
            "qts": int(self.qts),
            "date": int(self.date),
            "seq": int(self.seq),
        }
        if self.version >= 3:
            payload["channel_pts"] = {
                str(channel_id): int(pts) for channel_id, pts in sorted(self.channel_pts.items())
            }
        return payload

    @classmethod
    def from_json_dict(cls, data: dict[str, object]) -> PersistedUpdatesState:
        try:
            # Checkpoints without an explicit version predate authorization
            # binding, so they must receive the same explicit trust treatment
            # as v1 instead of being mistaken for the newest format.
            version_obj = data.get("version", 1)
            if isinstance(version_obj, bool) or not isinstance(version_obj, (int, str)):
                raise UpdatesStateStorageError("Invalid version")
            version = int(version_obj)
            if version not in _SUPPORTED_UPDATES_STATE_VERSIONS:
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
                if isinstance(v, bool) or not isinstance(v, (int, str)):
                    raise UpdatesStateStorageError(f"Invalid {k}")
                return int(v)

            pts = _need_int("pts")
            qts = _need_int("qts")
            date = _need_int("date")
            seq = _need_int("seq")

            channel_pts: dict[int, int] = {}
            if version >= 3:
                raw_channel_pts = data["channel_pts"]
                if not isinstance(raw_channel_pts, dict):
                    raise UpdatesStateStorageError("Invalid channel_pts")
                for raw_channel_id, raw_pts in raw_channel_pts.items():
                    if not isinstance(raw_channel_id, str) or not raw_channel_id.isdecimal():
                        raise UpdatesStateStorageError("Invalid channel id")
                    channel_id = int(raw_channel_id)
                    if channel_id in channel_pts:
                        raise UpdatesStateStorageError("Duplicate channel id")
                    if isinstance(raw_pts, bool) or not isinstance(raw_pts, (int, str)):
                        raise UpdatesStateStorageError(
                            f"Invalid channel pts for channel {channel_id}"
                        )
                    channel_pts[channel_id] = int(raw_pts)
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
            channel_pts=channel_pts,
            version=version,
        )
        out.validate()
        return out


def _load_persisted_updates_state_file(path: str | Path) -> PersistedUpdatesState:
    p = Path(path)
    raw = p.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except Exception as e:  # noqa: BLE001
        raise UpdatesStateStorageError(f"Failed to parse updates state JSON: {p}") from e
    if not isinstance(data, dict):
        raise UpdatesStateStorageError("Updates state JSON must be an object")
    return PersistedUpdatesState.from_json_dict(data)


def inspect_updates_state_file_auth_key_id(path: str | Path) -> str | None:
    """Return the validated authorization binding without trusting its counters."""

    return _load_persisted_updates_state_file(path).auth_key_id


def load_updates_state_file(
    path: str | Path,
    *,
    expected_auth_key_id: str | None = None,
    allow_unbound_legacy: bool = False,
) -> UpdatesState:
    persisted = _load_persisted_updates_state_file(path)
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
