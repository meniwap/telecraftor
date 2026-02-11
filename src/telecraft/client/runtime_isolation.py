from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

RuntimeMode = Literal["sandbox", "prod"]
NetworkMode = Literal["test", "prod"]


class RuntimeIsolationError(ValueError):
    """Raised when runtime/network/session isolation checks fail."""


# Mirrors client mtproto endpoint mappings; kept local to avoid touching core.
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
    legacy_current_pointer: Path
    audit_peer_file: Path
    legacy_audit_peer_file: Path


def _truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def resolve_runtime(raw: str | None, *, default: RuntimeMode = "sandbox") -> RuntimeMode:
    if raw is None or not raw.strip():
        return default
    v = raw.strip().lower()
    if v in {"sandbox", "test"}:
        return "sandbox"
    if v in {"prod", "production"}:
        return "prod"
    raise RuntimeIsolationError(f"Unknown runtime {raw!r}. Expected one of: sandbox, prod.")


def resolve_network(*, runtime: RuntimeMode | str, explicit_network: str | None) -> NetworkMode:
    rt = resolve_runtime(str(runtime))
    expected: NetworkMode = "test" if rt == "sandbox" else "prod"
    if explicit_network is None or not explicit_network.strip():
        return expected
    v = explicit_network.strip().lower()
    if v not in {"test", "prod"}:
        raise RuntimeIsolationError(
            f"Unknown network {explicit_network!r}. Expected one of: test, prod."
        )
    if v != expected:
        raise RuntimeIsolationError(
            "Runtime/network mismatch: "
            f"runtime={rt!r} maps to network={expected!r}, got --network={v!r}. "
            "Use the matching runtime/network pair."
        )
    return expected


def resolve_session_paths(
    *,
    runtime: RuntimeMode | str,
    network: NetworkMode | str,
    sessions_root: Path | str = ".sessions",
) -> SessionPaths:
    rt = resolve_runtime(str(runtime))
    nw = str(network).strip().lower()
    if nw not in {"test", "prod"}:
        raise RuntimeIsolationError(f"Unknown network {network!r}. Expected test/prod.")
    sessions_root_path = Path(sessions_root)
    runtime_root = sessions_root_path / ("sandbox" if rt == "sandbox" else "prod")
    return SessionPaths(
        runtime=rt,
        network=nw,  # type: ignore[arg-type]
        sessions_root=sessions_root_path,
        runtime_root=runtime_root,
        current_pointer=runtime_root / "current",
        legacy_current_pointer=sessions_root_path / f"{nw}.current",
        audit_peer_file=runtime_root / "live_audit_peer.txt",
        legacy_audit_peer_file=sessions_root_path / "live_audit_peer.txt",
    )


def default_session_path(paths: SessionPaths, *, dc: int) -> Path:
    return paths.runtime_root / f"{paths.network}_dc{int(dc)}.session.json"


def resolve_report_root(base_dir: Path | str, *, runtime: RuntimeMode | str) -> Path:
    rt = resolve_runtime(str(runtime))
    return Path(base_dir) / rt


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


def read_current_session(paths: SessionPaths) -> str | None:
    cur = _resolve_pointer_target(paths.current_pointer)
    if cur is not None:
        return cur
    return _resolve_pointer_target(paths.legacy_current_pointer)


def pick_latest_session(paths: SessionPaths) -> str | None:
    best: tuple[float, str] | None = None
    for root in (paths.runtime_root, paths.sessions_root):
        for dc in (1, 2, 3, 4, 5):
            p = root / f"{paths.network}_dc{dc}.session.json"
            if not p.exists():
                continue
            try:
                mtime = p.stat().st_mtime
            except OSError:
                continue
            if best is None or mtime > best[0]:
                best = (mtime, str(p.resolve()))
    return best[1] if best is not None else None


def pick_existing_session(paths: SessionPaths, *, preferred_dc: int) -> str:
    current = read_current_session(paths)
    if current is not None:
        return current
    preferred = default_session_path(paths, dc=preferred_dc)
    if preferred.exists():
        return str(preferred.resolve())
    latest = pick_latest_session(paths)
    if latest is not None:
        return latest
    return str(preferred.resolve())


def write_current_session_pointer(paths: SessionPaths, session_path: str | Path) -> None:
    p = Path(session_path).expanduser()
    if not p.is_absolute():
        p = (Path.cwd() / p).resolve()
    paths.runtime_root.mkdir(parents=True, exist_ok=True)
    paths.current_pointer.write_text(str(p) + "\n", encoding="utf-8", newline="\n")


def _host_to_network(host: str, session_name: str) -> NetworkMode | None:
    h = host.strip()
    if h in TEST_HOSTS:
        return "test"
    if h in PROD_HOSTS:
        return "prod"
    if session_name.startswith("test_"):
        return "test"
    if session_name.startswith("prod_"):
        return "prod"
    return None


def validate_session_matches_network(
    *,
    session_path: str | Path,
    expected_network: NetworkMode | str,
) -> None:
    p = Path(session_path).expanduser()
    if not p.exists():
        return
    expected = str(expected_network).strip().lower()
    if expected not in {"test", "prod"}:
        raise RuntimeIsolationError(f"Unknown expected network {expected_network!r}.")

    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        raise RuntimeIsolationError(f"Invalid session JSON at {p}: {type(e).__name__}: {e}") from e

    host_raw = payload.get("host", "")
    host = str(host_raw).strip()
    actual = _host_to_network(host, p.name)
    if actual is None:
        return
    if actual != expected:
        raise RuntimeIsolationError(
            "Session/network mismatch: "
            f"session={p} host={host!r} resolved_network={actual!r}, expected={expected!r}. "
            "Use a session for the expected network or switch runtime."
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
