from __future__ import annotations

import asyncio
import json
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
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


def resolve_live_audit_peer(ctx: Any) -> str | None:
    peer = str(getattr(ctx.cfg, "audit_peer", "auto")).strip()
    if not peer or peer == "auto":
        return None
    return peer


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
        "source_commit": ctx.source_commit,
        "source_tree_clean": ctx.source_tree_clean,
        "ts": datetime.now(timezone.utc).isoformat(),
        "pass_count": pass_count,
        "fail_count": fail_count,
        # The release manifest deliberately carries only the count.  Detailed
        # cleanup failures remain in the local summary below and are never
        # copied into the sanitized, committable evidence file.
        "cleanup_errors": len(cleanup_errors),
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
        f"- source_commit: `{ctx.source_commit}`",
        f"- source_tree_clean: `{ctx.source_tree_clean}`",
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
    except Exception as exc:  # noqa: BLE001
        close_error = f"client.close: {type(exc).__name__}: {exc}"
        cleanup_errors.append(close_error)
        summary["cleanup_errors"] = len(cleanup_errors)
        (ctx.run_dir / "artifacts.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        if "## Cleanup Errors" not in lines:
            lines.extend(["", "## Cleanup Errors"])
        lines.append(f"- {close_error}")
        (ctx.run_dir / "summary.md").write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    if fail_count > 0:
        raise AssertionError(f"Live suite had {fail_count} failed steps; see {ctx.run_dir}")
    if cleanup_errors:
        raise AssertionError(
            f"Live suite had {len(cleanup_errors)} cleanup errors; see {ctx.run_dir}"
        )
    return summary
