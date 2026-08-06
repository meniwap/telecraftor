from __future__ import annotations

import base64
import json
import os
import socket
import time
from dataclasses import dataclass
from pathlib import Path

from telecraft._private_storage import atomic_write_private_text

_SESSION_VERSION = 1


class SessionError(Exception):
    pass


class SessionInUseError(SessionError):
    """Raised when another process already owns a session file lease."""


@dataclass(slots=True)
class SessionFileLock:
    """Process-scoped advisory lock held for a client's connected lifetime."""

    path: Path
    fd: int
    backend: str
    released: bool = False

    def release(self) -> None:
        if self.released:
            return
        self.released = True
        try:
            if self.backend == "fcntl":
                import fcntl

                fcntl.flock(self.fd, fcntl.LOCK_UN)
            elif self.backend == "msvcrt":
                import msvcrt

                os.lseek(self.fd, 0, os.SEEK_SET)
                getattr(msvcrt, "locking")(self.fd, getattr(msvcrt, "LK_UNLCK"), 1)
        finally:
            os.close(self.fd)

    def __enter__(self) -> SessionFileLock:
        return self

    def __exit__(self, *_args: object) -> None:
        self.release()


def acquire_session_file_lock(path: str | Path) -> SessionFileLock:
    """Acquire a non-blocking, crash-safe lock for a session file.

    The lock uses the operating system rather than a PID-only sentinel, so it is
    released automatically if a process crashes.  The small ``.lock`` file is
    intentionally retained: unlinking an advisory lock file creates a race where
    two processes can lock different inodes under the same pathname.
    """

    session_path = Path(path).expanduser()
    lock_path = session_path.with_name(session_path.name + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    fd = os.open(lock_path, flags, 0o600)
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(fd, 0o600)

        backend: str
        try:
            import fcntl
        except ImportError:
            try:
                import msvcrt
            except ImportError as exc:  # pragma: no cover - supported platforms provide one
                raise SessionError("This platform does not provide advisory file locking") from exc

            # Windows byte-range locks require the byte to exist.
            if os.fstat(fd).st_size == 0:
                os.write(fd, b"\x00")
            os.lseek(fd, 0, os.SEEK_SET)
            try:
                getattr(msvcrt, "locking")(fd, getattr(msvcrt, "LK_NBLCK"), 1)
            except OSError as exc:
                raise SessionInUseError(
                    f"Session is already in use by another process: {session_path}"
                ) from exc
            backend = "msvcrt"
        else:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise SessionInUseError(
                    f"Session is already in use by another process: {session_path}"
                ) from exc
            backend = "fcntl"

        metadata = json.dumps(
            {
                "pid": os.getpid(),
                "hostname": socket.gethostname(),
                "session": str(session_path.resolve()),
                "acquired_at": int(time.time()),
            },
            sort_keys=True,
        ).encode("utf-8")
        os.lseek(fd, 0, os.SEEK_SET)
        payload = metadata + b"\n"
        written = 0
        while written < len(payload):
            count = os.write(fd, payload[written:])
            if count <= 0:
                raise OSError("Failed to write session lock metadata")
            written += count
        os.ftruncate(fd, len(payload))
        os.fsync(fd)
        return SessionFileLock(path=lock_path, fd=fd, backend=backend)
    except BaseException:
        os.close(fd)
        raise


@dataclass(slots=True)
class MtprotoSession:
    """
    Minimal MTProto session persistence.

    This intentionally stores only what we need to avoid re-doing the auth key exchange:
    - dc endpoint + framing (so we don't accidentally reuse a key for the wrong DC)
    - auth_key
    - server_salt
    - session_id (optional; if absent, a new one will be generated)
    """

    dc_id: int
    host: str
    port: int
    framing: str  # "intermediate" | "abridged"
    auth_key: bytes
    server_salt: bytes  # 8 bytes little-endian
    session_id: bytes | None = None  # 8 bytes
    updates_state_auth_key_id_alias: str | None = None
    version: int = _SESSION_VERSION

    def validate(self) -> None:
        if self.version != _SESSION_VERSION:
            raise SessionError(f"Unsupported session version: {self.version}")
        if not isinstance(self.dc_id, int) or self.dc_id <= 0:
            raise SessionError("Invalid dc_id")
        if not self.host:
            raise SessionError("Invalid host")
        if not isinstance(self.port, int) or not (0 < self.port < 65536):
            raise SessionError("Invalid port")
        if self.framing not in {"intermediate", "abridged"}:
            raise SessionError("Invalid framing")
        if not isinstance(self.auth_key, (bytes, bytearray)) or len(self.auth_key) != 256:
            raise SessionError("Invalid auth_key (must be 256 bytes)")
        if not isinstance(self.server_salt, (bytes, bytearray)) or len(self.server_salt) != 8:
            raise SessionError("Invalid server_salt (must be 8 bytes)")
        if self.session_id is not None and len(self.session_id) != 8:
            raise SessionError("Invalid session_id (must be 8 bytes)")
        if self.updates_state_auth_key_id_alias is not None:
            value = self.updates_state_auth_key_id_alias.casefold()
            if len(value) != 16 or any(char not in "0123456789abcdef" for char in value):
                raise SessionError("Invalid updates_state_auth_key_id_alias")
            self.updates_state_auth_key_id_alias = value

    def to_json_dict(self) -> dict[str, object]:
        self.validate()
        return {
            "version": self.version,
            "dc_id": self.dc_id,
            "host": self.host,
            "port": self.port,
            "framing": self.framing,
            "auth_key_b64": base64.b64encode(self.auth_key).decode("ascii"),
            "server_salt_hex": self.server_salt.hex(),
            "session_id_hex": self.session_id.hex() if self.session_id is not None else None,
            "updates_state_auth_key_id_alias": self.updates_state_auth_key_id_alias,
        }

    @classmethod
    def from_json_dict(cls, data: dict[str, object]) -> MtprotoSession:
        try:
            version_obj = data.get("version", _SESSION_VERSION)
            if not isinstance(version_obj, (int, str)):
                raise SessionError("Invalid version")
            version = int(version_obj)

            dc_id_obj = data["dc_id"]
            if not isinstance(dc_id_obj, (int, str)):
                raise SessionError("Invalid dc_id")
            dc_id = int(dc_id_obj)

            host_obj = data["host"]
            if not isinstance(host_obj, str):
                raise SessionError("Invalid host")
            host = host_obj

            port_obj = data["port"]
            if not isinstance(port_obj, (int, str)):
                raise SessionError("Invalid port")
            port = int(port_obj)

            framing_obj = data["framing"]
            if not isinstance(framing_obj, str):
                raise SessionError("Invalid framing")
            framing = framing_obj

            auth_key_b64_obj = data["auth_key_b64"]
            if not isinstance(auth_key_b64_obj, str):
                raise SessionError("Invalid auth_key_b64")
            auth_key_b64 = auth_key_b64_obj

            server_salt_hex_obj = data["server_salt_hex"]
            if not isinstance(server_salt_hex_obj, str):
                raise SessionError("Invalid server_salt_hex")
            server_salt_hex = server_salt_hex_obj

            session_id_hex = data.get("session_id_hex")
            updates_state_auth_key_id_alias_obj = data.get("updates_state_auth_key_id_alias")
            if updates_state_auth_key_id_alias_obj is not None and not isinstance(
                updates_state_auth_key_id_alias_obj,
                str,
            ):
                raise SessionError("Invalid updates_state_auth_key_id_alias")
            updates_state_auth_key_id_alias = updates_state_auth_key_id_alias_obj
        except Exception as e:  # noqa: BLE001
            raise SessionError("Invalid session JSON shape") from e

        try:
            auth_key = base64.b64decode(auth_key_b64.encode("ascii"))
        except Exception as e:  # noqa: BLE001
            raise SessionError("Invalid auth_key_b64") from e

        try:
            server_salt = bytes.fromhex(server_salt_hex)
        except Exception as e:  # noqa: BLE001
            raise SessionError("Invalid server_salt_hex") from e

        session_id: bytes | None
        if session_id_hex is None:
            session_id = None
        else:
            try:
                if not isinstance(session_id_hex, str):
                    raise SessionError("Invalid session_id_hex")
                session_id = bytes.fromhex(session_id_hex)
            except Exception as e:  # noqa: BLE001
                raise SessionError("Invalid session_id_hex") from e

        sess = cls(
            version=version,
            dc_id=dc_id,
            host=host,
            port=port,
            framing=framing,
            auth_key=auth_key,
            server_salt=server_salt,
            session_id=session_id,
            updates_state_auth_key_id_alias=updates_state_auth_key_id_alias,
        )
        sess.validate()
        return sess


def load_session_file(path: str | Path) -> MtprotoSession:
    p = Path(path)
    raw = p.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except Exception as e:  # noqa: BLE001
        raise SessionError(f"Failed to parse session JSON: {p}") from e
    if not isinstance(data, dict):
        raise SessionError("Session JSON must be an object")
    return MtprotoSession.from_json_dict(data)


def save_session_file(path: str | Path, session: MtprotoSession) -> None:
    session.validate()
    atomic_write_private_text(
        path,
        json.dumps(session.to_json_dict(), indent=2, sort_keys=True) + "\n",
    )
