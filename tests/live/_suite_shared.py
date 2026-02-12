from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from telecraft.client import Client


@dataclass(slots=True)
class StepResult:
    name: str
    status: str
    details: str


async def run_step(
    *,
    name: str,
    fn: Callable[[], Awaitable[str]],
    client: Client,
    reporter: Any,
    results: list[StepResult],
) -> None:
    await reporter.emit(client=client, status="START", step=name, details="")
    try:
        details = await fn()
        results.append(StepResult(name=name, status="PASS", details=details))
        await reporter.emit(client=client, status="PASS", step=name, details=details)
    except Exception as e:  # noqa: BLE001
        details = f"{type(e).__name__}: {e}"
        results.append(StepResult(name=name, status="FAIL", details=details))
        await reporter.emit(client=client, status="FAIL", step=name, details=details)


async def resolve_or_create_audit_peer(client: Client, ctx: Any, reporter: Any) -> str:
    if ctx.cfg.audit_peer != "auto":
        return ctx.cfg.audit_peer

    cfg_file = Path(ctx.cfg.audit_peer_file)
    if cfg_file.exists():
        s = cfg_file.read_text(encoding="utf-8").strip()
        if s:
            return s
    legacy = Path(".sessions/live_audit_peer.txt")
    if legacy.exists():
        s = legacy.read_text(encoding="utf-8").strip()
        if s:
            cfg_file.parent.mkdir(parents=True, exist_ok=True)
            cfg_file.write_text(s + "\n", encoding="utf-8", newline="\n")
            return s

    created = await client.chats.create_channel(
        title="telecraft-audit-v3",
        about="Telecraft V3 live audit log stream",
        broadcast=False,
        megagroup=True,
        timeout=ctx.cfg.timeout,
    )
    cid = extract_channel_id(created)
    if cid is None:
        raise RuntimeError("Failed to create audit group/channel")

    peer = f"channel:{cid}"
    cfg_file.parent.mkdir(parents=True, exist_ok=True)
    cfg_file.write_text(peer + "\n", encoding="utf-8", newline="\n")
    await reporter.emit(
        client=client,
        status="PASS",
        step="audit-provision",
        details=f"Created persistent audit peer {peer!r}",
        to_telegram=False,
    )
    return peer


def extract_message_id(obj: Any) -> int | None:
    updates = getattr(obj, "updates", None)
    if isinstance(updates, list):
        for u in updates:
            msg = getattr(u, "message", None)
            mid = getattr(msg, "id", None)
            if isinstance(mid, int):
                return mid
    mid = getattr(obj, "id", None)
    return int(mid) if isinstance(mid, int) else None


def extract_chat_id(obj: Any) -> int | None:
    sources = [obj, getattr(obj, "updates", None)]
    for src in sources:
        chats = getattr(src, "chats", None)
        if not isinstance(chats, list):
            continue
        for c in chats:
            if getattr(c, "TL_NAME", "") in {"chat", "chatForbidden"}:
                cid = getattr(c, "id", None)
                if isinstance(cid, int):
                    return int(cid)
    return None


def extract_channel_id(obj: Any) -> int | None:
    sources = [obj, getattr(obj, "updates", None)]
    for src in sources:
        chats = getattr(src, "chats", None)
        if not isinstance(chats, list):
            continue
        for c in chats:
            if getattr(c, "TL_NAME", "") in {"channel", "channelForbidden"}:
                cid = getattr(c, "id", None)
                if isinstance(cid, int):
                    return int(cid)
    return None


def parse_user_id(peer: Any) -> int:
    uid = getattr(peer, "peer_id", None)
    if not isinstance(uid, int):
        raise RuntimeError("Expected second account to resolve to a user peer")
    return int(uid)


def is_private_or_not_found_error(err: Exception) -> bool:
    msg = str(err).upper()
    return any(
        token in msg
        for token in (
            "CHANNEL_PRIVATE",
            "CHANNEL_INVALID",
            "CHAT_ID_INVALID",
            "PEER_ID_INVALID",
        )
    )


def is_chat_write_forbidden_error(err: Exception) -> bool:
    return "CHAT_WRITE_FORBIDDEN" in str(err).upper()


def is_schema_decode_mismatch_error(err: Exception) -> bool:
    msg = str(err)
    upper = msg.upper()
    return (
        "UNKNOWN CONSTRUCTOR ID" in upper
        or "RECEIVER LOOP CRASHED" in upper
        or type(err).__name__ in {"RpcSenderError", "TLCodecError"}
    )


async def create_temp_write_peer(
    *,
    client: Client,
    ctx: Any,
    resource_ids: dict[str, object],
    key_prefix: str,
) -> str:
    created = await client.chats.create_channel(
        title=f"tc-live-{key_prefix}-{ctx.run_id}",
        about="Telecraft live writable peer",
        broadcast=False,
        megagroup=True,
        timeout=ctx.cfg.timeout,
    )
    cid = extract_channel_id(created)
    if cid is None:
        raise RuntimeError("Failed to create temporary writable channel")
    peer = f"channel:{cid}"
    resource_ids[f"{key_prefix}_peer"] = peer

    async def _cleanup() -> None:
        await client.chats.delete_channel(peer, timeout=ctx.cfg.timeout)

    ctx.add_cleanup(_cleanup)
    return peer


async def finalize_run(
    *,
    client: Client,
    ctx: Any,
    reporter: Any,
    results: list[StepResult],
    resource_ids: dict[str, object],
) -> dict[str, Any]:
    cleanup_errors = await ctx.run_cleanups()
    pass_count = len([r for r in results if r.status == "PASS"])
    fail_count = len([r for r in results if r.status == "FAIL"])
    summary = {
        "run_id": ctx.run_id,
        "ts": datetime.now(timezone.utc).isoformat(),
        "pass_count": pass_count,
        "fail_count": fail_count,
        "cleanup_errors": cleanup_errors,
        "resources": resource_ids,
        "steps": [
            {
                "name": r.name,
                "status": r.status,
                "details": r.details,
            }
            for r in results
        ],
    }
    (ctx.run_dir / "artifacts.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    lines = [
        "# Telecraft Live Report",
        "",
        f"- run_id: `{ctx.run_id}`",
        f"- pass: `{pass_count}`",
        f"- fail: `{fail_count}`",
        f"- cleanup_errors: `{len(cleanup_errors)}`",
        "",
        "## Steps",
    ]
    for r in results:
        lines.append(f"- {r.status} `{r.name}`: {r.details}")
    if cleanup_errors:
        lines.append("")
        lines.append("## Cleanup Errors")
        for e in cleanup_errors:
            lines.append(f"- {e}")
    (ctx.run_dir / "summary.md").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    await reporter.emit(
        client=client,
        status="SUMMARY",
        step="run",
        details=(
            f"pass={pass_count} fail={fail_count} cleanup_errors={len(cleanup_errors)} "
            f"resources={json.dumps(resource_ids, ensure_ascii=False)}"
        ),
        to_telegram=True,
    )
    await reporter.close()
    try:
        await asyncio.wait_for(
            client.close(),
            timeout=min(float(ctx.cfg.timeout), 10.0),
        )
    except Exception:  # noqa: BLE001
        pass

    if fail_count > 0:
        raise AssertionError(f"Live suite had {fail_count} failed steps; see {ctx.run_dir}")
    return summary
