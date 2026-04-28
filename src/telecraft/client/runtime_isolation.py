from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

RuntimeMode = Literal["prod"]
NetworkMode = Literal["prod"]
SessionKind = Literal["user", "bot"]


class RuntimeIsolationError(ValueError):
    """Raised when runtime/session policy checks fail."""


# Kept local to avoid touching core. Test-network sessions are rejected here.
TEST_HOSTS = {
    "149.154.175.10",
    "149.154.167.40",
    "149.154.175.117",
}
PROD_HOSTS = {
    "149.154.175.50",
    "149.154.167.51",
    "149.154.175.100",
    "149.154.167.91",
    "91.108.56.130",
}


@dataclass(frozen=True, slots=True)
class SessionPaths:
    runtime: RuntimeMode
    network: NetworkMode
    sessions_root: Path
    runtime_root: Path
    current_pointer: Path
    current_bot_pointer: Path
    legacy_current_pointer: Path
    legacy_current_bot_pointer: Path
    audit_peer_file: Path
    legacy_audit_peer_file: Path


def _truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def resolve_session_kind(raw: str | None, *, default: SessionKind = "user") -> SessionKind:
    if raw is None or not raw.strip():
        return default
    v = raw.strip().lower()
    if v in {"user", "account"}:
        return "user"
    if v in {"bot", "bot_account"}:
        return "bot"
    raise RuntimeIsolationError(f"Unknown session kind {raw!r}. Expected one of: user, bot.")


def resolve_runtime(raw: str | None, *, default: RuntimeMode = "prod") -> RuntimeMode:
    if raw is None or not raw.strip():
        return default
    v = raw.strip().lower()
    if v in {"prod", "production"}:
        return "prod"
    if v in {"sandbox", "test"}:
        raise RuntimeIsolationError(
            "Sandbox/test runtime was removed from Telecraft's public workflow. "
            "Use prod sessions under .sessions/prod/."
        )
    raise RuntimeIsolationError(f"Unknown runtime {raw!r}. Expected: prod.")


def resolve_network(*, runtime: RuntimeMode | str, explicit_network: str | None) -> NetworkMode:
    _ = resolve_runtime(str(runtime), default="prod")
    if explicit_network is None or not explicit_network.strip():
        return "prod"
    v = explicit_network.strip().lower()
    if v == "prod":
        return "prod"
    raise RuntimeIsolationError(
        f"Network {explicit_network!r} is not supported by public orchestration. Use prod."
    )


def resolve_session_paths(
    *,
    runtime: RuntimeMode | str = "prod",
    network: NetworkMode | str = "prod",
    sessions_root: Path | str = ".sessions",
) -> SessionPaths:
    rt = resolve_runtime(str(runtime), default="prod")
    nw = str(network).strip().lower()
    if nw != "prod":
        raise RuntimeIsolationError(f"Network {network!r} is not supported. Expected prod.")
    sessions_root_path = Path(sessions_root)
    runtime_root = sessions_root_path / "prod"
    return SessionPaths(
        runtime=rt,
        network="prod",
        sessions_root=sessions_root_path,
        runtime_root=runtime_root,
        current_pointer=runtime_root / "current",
        current_bot_pointer=runtime_root / "current_bot",
        legacy_current_pointer=sessions_root_path / "prod.current",
        legacy_current_bot_pointer=sessions_root_path / "prod.bot.current",
        audit_peer_file=runtime_root / "live_audit_peer.txt",
        legacy_audit_peer_file=sessions_root_path / "live_audit_peer.txt",
    )


def default_session_path(paths: SessionPaths, *, dc: int, kind: SessionKind = "user") -> Path:
    resolved_kind = resolve_session_kind(kind)
    if resolved_kind == "bot":
        return paths.runtime_root / f"prod_dc{int(dc)}.bot.session.json"
    return paths.runtime_root / f"prod_dc{int(dc)}.session.json"


def resolve_report_root(base_dir: Path | str, *, runtime: RuntimeMode | str = "prod") -> Path:
    _ = resolve_runtime(str(runtime), default="prod")
    return Path(base_dir) / "prod"


def _resolve_pointer_target(pointer_file: Path) -> str | None:
    if not pointer_file.exists():
        return None
    target = pointer_file.read_text(encoding="utf-8").strip()
    if not target:
        return None
    p = Path(target).expanduser()
    if not p.is_absolute():
        p = (Path.cwd() / p).resolve()
    if p.exists():
        return str(p)
    return None


def read_current_session(paths: SessionPaths, *, kind: SessionKind = "user") -> str | None:
    resolved_kind = resolve_session_kind(kind)
    if resolved_kind == "bot":
        cur = _resolve_pointer_target(paths.current_bot_pointer)
        if cur is not None:
            return cur
        return _resolve_pointer_target(paths.legacy_current_bot_pointer)

    cur = _resolve_pointer_target(paths.current_pointer)
    if cur is not None:
        return cur
    return _resolve_pointer_target(paths.legacy_current_pointer)


def pick_latest_session(paths: SessionPaths, *, kind: SessionKind = "user") -> str | None:
    resolved_kind = resolve_session_kind(kind)
    suffix = ".bot.session.json" if resolved_kind == "bot" else ".session.json"
    best: tuple[float, str] | None = None
    for root in (paths.runtime_root, paths.sessions_root):
        for dc in (1, 2, 3, 4, 5):
            p = root / f"prod_dc{dc}{suffix}"
            if not p.exists():
                continue
            try:
                mtime = p.stat().st_mtime
            except OSError:
                continue
            if best is None or mtime > best[0]:
                best = (mtime, str(p.resolve()))
    return best[1] if best is not None else None


def pick_existing_session(
    paths: SessionPaths,
    *,
    preferred_dc: int,
    kind: SessionKind = "user",
) -> str:
    resolved_kind = resolve_session_kind(kind)
    current = read_current_session(paths, kind=resolved_kind)
    if current is not None:
        return current
    preferred = default_session_path(paths, dc=preferred_dc, kind=resolved_kind)
    if preferred.exists():
        return str(preferred.resolve())
    latest = pick_latest_session(paths, kind=resolved_kind)
    if latest is not None:
        return latest
    return str(preferred.resolve())


def write_current_session_pointer(
    paths: SessionPaths,
    session_path: str | Path,
    *,
    kind: SessionKind = "user",
) -> None:
    resolved_kind = resolve_session_kind(kind)
    p = Path(session_path).expanduser()
    if not p.is_absolute():
        p = (Path.cwd() / p).resolve()
    paths.runtime_root.mkdir(parents=True, exist_ok=True)
    pointer_path = paths.current_bot_pointer if resolved_kind == "bot" else paths.current_pointer
    pointer_path.write_text(str(p) + "\n", encoding="utf-8", newline="\n")


def _host_to_network(host: str, session_name: str) -> str | None:
    h = host.strip()
    if h in TEST_HOSTS or session_name.startswith("test_"):
        return "test"
    if h in PROD_HOSTS or session_name.startswith("prod_"):
        return "prod"
    return None


def validate_session_matches_network(
    *,
    session_path: str | Path,
    expected_network: NetworkMode | str = "prod",
) -> None:
    p = Path(session_path).expanduser()
    if not p.exists():
        return
    expected = str(expected_network).strip().lower()
    if expected != "prod":
        raise RuntimeIsolationError(
            f"Network {expected_network!r} is not supported. Expected prod."
        )

    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        raise RuntimeIsolationError(f"Invalid session JSON at {p}: {type(e).__name__}: {e}") from e

    host = str(payload.get("host", "")).strip()
    actual = _host_to_network(host, p.name)
    if actual is None:
        return
    if actual != "prod":
        raise RuntimeIsolationError(
            "Session/network mismatch: "
            f"session={p} host={host!r} resolved_network={actual!r}, expected='prod'. "
            "Use a prod session under .sessions/prod/."
        )


def require_prod_override(
    *,
    allow_flag: bool,
    env_var: str,
    action: str,
    example: str,
) -> None:
    if allow_flag and _truthy(os.environ.get(env_var)):
        return
    raise RuntimeIsolationError(
        f"Production access blocked for {action}. "
        f"To proceed, pass the required flag and set {env_var}=1.\n"
        f"Example:\n{example}"
    )
