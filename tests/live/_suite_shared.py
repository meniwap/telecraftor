from __future__ import annotations

import asyncio
import json
from collections import Counter
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
    error_class: str | None = None
    health_probe: str | None = None


def classify_live_error(err: Exception) -> str:
    name = type(err).__name__
    msg = str(err)
    upper = msg.upper()

    if isinstance(err, asyncio.TimeoutError) or "TIMEOUT" in upper:
        return "timeout"

    if name in {"RpcDecodeError", "TLCodecError"} or (
        "UNKNOWN CONSTRUCTOR ID" in upper or "RECEIVER LOOP CRASHED" in upper
    ):
        return "decode"

    if isinstance(err, (ConnectionError, OSError)) or any(
        token in upper
        for token in (
            "CONNECTION RESET",
            "BROKEN PIPE",
            "TRANSPORT",
            "DISCONNECTED",
            "CONNECTION ABORTED",
        )
    ):
        return "transport"

    if name == "FloodWaitError" or "FLOOD_WAIT" in upper or "SLOWMODE_WAIT" in upper:
        return "rpc"

    if name == "RpcErrorException" or upper.startswith("RPC_ERROR "):
        capability_tokens = (
            "METHOD_INVALID",
            "NOT_SUPPORTED",
            "TAKEOUT_REQUIRED",
            "PREMIUM_ACCOUNT_REQUIRED",
            "BUSINESS",
            "PASSKEY",
            "FEATURE",
        )
        if any(token in upper for token in capability_tokens):
            return "capability"
        return "rpc"

    return "unknown"


def _is_prod_safe_profile(reporter: Any) -> bool:
    cfg = getattr(getattr(reporter, "ctx", None), "cfg", None)
    return bool(cfg is not None and getattr(cfg, "live_profile", "default") == "prod_safe")


def _record_health_probe(reporter: Any, *, passed: bool) -> None:
    ctx = getattr(reporter, "ctx", None)
    if ctx is None:
        return
    probes = ctx.artifacts.setdefault(
        "connection_health_probes",
        {
            "enabled": True,
            "probe": "profile.me",
            "pass": 0,
            "fail": 0,
        },
    )
    if not isinstance(probes, dict):
        return
    key = "pass" if passed else "fail"
    probes[key] = int(probes.get(key, 0)) + 1


async def run_health_probe(*, client: Client, reporter: Any) -> str:
    cfg = getattr(getattr(reporter, "ctx", None), "cfg", None)
    timeout = min(float(getattr(cfg, "timeout", 20.0)), 10.0)
    me = await client.profile.me(timeout=timeout)
    uid = getattr(me, "id", None)
    if isinstance(uid, int):
        return f"profile.me id={uid}"
    return f"profile.me type={type(me).__name__}"


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
        health_probe_status: str | None = None
        if _is_prod_safe_profile(reporter):
            try:
                probe_details = await run_health_probe(client=client, reporter=reporter)
                _record_health_probe(reporter, passed=True)
                health_probe_status = f"PASS: {probe_details}"
            except Exception as probe_err:  # noqa: BLE001
                _record_health_probe(reporter, passed=False)
                error_class = classify_live_error(probe_err)
                probe_details = f"{type(probe_err).__name__}: {probe_err}"
                results.append(
                    StepResult(
                        name=name,
                        status="FAIL_HEALTH",
                        details=f"{details} | health_probe={probe_details}",
                        error_class=error_class,
                        health_probe=f"FAIL: {probe_details}",
                    )
                )
                await reporter.emit(
                    client=client,
                    status="FAIL_HEALTH",
                    step=name,
                    details=f"{details} | health_probe={probe_details}",
                    error_class=error_class,
                )
                return
        results.append(
            StepResult(
                name=name,
                status="PASS",
                details=details,
                health_probe=health_probe_status,
            )
        )
        await reporter.emit(client=client, status="PASS", step=name, details=details)
    except Exception as e:  # noqa: BLE001
        details = f"{type(e).__name__}: {e}"
        error_class = classify_live_error(e)
        results.append(
            StepResult(
                name=name,
                status="FAIL",
                details=details,
                error_class=error_class,
            )
        )
        await reporter.emit(
            client=client,
            status="FAIL",
            step=name,
            details=details,
            error_class=error_class,
        )


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
    fail_count = len([r for r in results if str(r.status).startswith("FAIL")])
    error_breakdown = dict(Counter(r.error_class for r in results if r.error_class))
    if "connection_health_probes" not in ctx.artifacts:
        ctx.artifacts["connection_health_probes"] = {
            "enabled": False,
            "probe": "profile.me",
            "pass": 0,
            "fail": 0,
        }
    summary = {
        "run_id": ctx.run_id,
        "ts": datetime.now(timezone.utc).isoformat(),
        "pass_count": pass_count,
        "fail_count": fail_count,
        "cleanup_errors": cleanup_errors,
        "error_breakdown": error_breakdown,
        "resources": resource_ids,
        "connection_health_probes": ctx.artifacts.get("connection_health_probes"),
        "steps": [
            {
                "name": r.name,
                "status": r.status,
                "details": r.details,
                "error_class": r.error_class,
                "health_probe": r.health_probe,
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
    if error_breakdown:
        lines.append("")
        lines.append("## Error Class Breakdown")
        for key in sorted(error_breakdown):
            lines.append(f"- {key}: `{error_breakdown[key]}`")
    probes = summary.get("connection_health_probes")
    if isinstance(probes, dict):
        lines.append("")
        lines.append("## Connection Health Probes")
        lines.append(f"- enabled: `{probes.get('enabled')}`")
        lines.append(f"- probe: `{probes.get('probe')}`")
        lines.append(f"- pass: `{probes.get('pass')}`")
        lines.append(f"- fail: `{probes.get('fail')}`")
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
