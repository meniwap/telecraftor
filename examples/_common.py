from __future__ import annotations

import os

from telecraft.client import Client, ClientInit

DEFAULT_SESSION_PATH = ".sessions/prod/current"


def need_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"Missing {name}; export it before running this example.")
    return value


def build_client(*, session_path: str | None = None, network: str = "prod") -> Client:
    return Client(
        network=network,
        session_path=session_path or os.environ.get("TELECRAFT_SESSION_PATH", DEFAULT_SESSION_PATH),
        init=ClientInit(
            api_id=int(need_env("TELEGRAM_API_ID")),
            api_hash=need_env("TELEGRAM_API_HASH"),
        ),
    )
