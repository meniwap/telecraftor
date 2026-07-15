"""
Shared helpers for the Telecraft examples.

Every example builds its client here so the setup stays in one place:
- credentials come from TELEGRAM_API_ID / TELEGRAM_API_HASH
  (falling back to apps/env.sh when present, so local runs "just work")
- the session is loaded from TELECRAFT_SESSION_PATH or .sessions/prod/current

To create a session in the first place, see the Login section of the README.
"""

from __future__ import annotations

import os
from pathlib import Path

from telecraft.client import Client, ClientInit

DEFAULT_SESSION_PATH = ".sessions/prod/current"
_ENV_FILE = Path(__file__).resolve().parent.parent / "apps" / "env.sh"


def _load_env_file(path: Path) -> None:
    """Best-effort load of `export KEY=VALUE` lines into os.environ."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


def need_env(name: str) -> str:
    if name not in os.environ:
        _load_env_file(_ENV_FILE)
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"Missing {name}; export it before running this example.")
    return value


def allow_outgoing() -> bool:
    """
    Self-test switch shared by the bot examples.

    With TELECRAFT_ALLOW_OUTGOING=1 the dispatcher also reacts to messages you
    send yourself (e.g. in Saved Messages), so you can try a bot without a
    second account. Leave it unset for real-bot behavior (incoming only).
    """
    return os.environ.get("TELECRAFT_ALLOW_OUTGOING", "").strip() in {"1", "true", "yes"}


def _resolve_session(path: str) -> str:
    """
    Follow session pointer files.

    `.sessions/prod/current` holds the path of the active session file rather
    than the session itself; resolve it so examples work out of the box.
    """
    p = Path(path)
    try:
        if p.is_file() and p.stat().st_size < 512:
            text = p.read_text(encoding="utf-8").strip()
            if text.endswith(".json") and Path(text).is_file():
                return text
    except OSError:
        pass
    return path


def build_client(*, session_path: str | None = None, network: str = "prod") -> Client:
    return Client(
        network=network,
        session_path=_resolve_session(
            session_path or os.environ.get("TELECRAFT_SESSION_PATH", DEFAULT_SESSION_PATH)
        ),
        init=ClientInit(
            api_id=int(need_env("TELEGRAM_API_ID")),
            api_hash=need_env("TELEGRAM_API_HASH"),
        ),
    )
