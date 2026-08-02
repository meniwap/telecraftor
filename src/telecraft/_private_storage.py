from __future__ import annotations

import contextlib
import os
from pathlib import Path
from uuid import uuid4


def fsync_directory(path: str | Path) -> None:
    """Best-effort durability barrier for a completed atomic replacement."""

    directory = Path(path)
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC

    try:
        fd = os.open(directory, flags)
    except OSError:
        # Opening directories is not supported uniformly (notably on Windows).
        return
    try:
        with contextlib.suppress(OSError):
            os.fsync(fd)
    finally:
        with contextlib.suppress(OSError):
            os.close(fd)


def ensure_private_file(path: str | Path) -> Path:
    """Create *path* with mode 0600, and tighten an existing file when possible."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC

    fd = os.open(target, flags, 0o600)
    try:
        # A pre-existing database may have been created under a permissive umask.
        # Tighten the open inode before handing it to another library.
        if hasattr(os, "fchmod"):
            os.fchmod(fd, 0o600)
    finally:
        os.close(fd)
    return target


def atomic_write_private_text(path: str | Path, data: str) -> None:
    """Atomically replace *path* with UTF-8 text created private from byte zero."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f"{target.name}.{os.getpid()}.{uuid4().hex}.tmp")

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC

    fd: int | None = None
    try:
        # The creation mode is restrictive before any authorization or peer data
        # is written. A process umask may remove permissions but cannot add them.
        fd = os.open(tmp, flags, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            fd = None  # fdopen owns and closes it from this point onward.
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, target)
        fsync_directory(target.parent)
    except BaseException:
        if fd is not None:
            with contextlib.suppress(OSError):
                os.close(fd)
        with contextlib.suppress(FileNotFoundError, OSError):
            tmp.unlink()
        raise
