from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path
from typing import Any

import pytest

from telecraft.client import Client
from tests.live._suite_shared import finalize_run, resolve_or_create_audit_peer, run_step

pytestmark = [pytest.mark.live, pytest.mark.live_optional]


async def _run_uploads_suite(client: Client, ctx: Any, reporter: Any) -> None:
    if os.environ.get("TELECRAFT_LIVE_UPLOADS_ENABLE", "").strip() != "1":
        pytest.skip("Set TELECRAFT_LIVE_UPLOADS_ENABLE=1 to enable optional uploads live suite")

    await client.connect(timeout=ctx.cfg.timeout)
    results: list[Any] = []
    resource_ids: dict[str, object] = {}

    reporter.audit_peer = await resolve_or_create_audit_peer(client, ctx, reporter)
    await reporter.emit(
        client=client,
        status="START",
        step="run",
        details=f"run_id={ctx.run_id} lane=optional-uploads",
    )

    async def step_uploads_upload_file_roundtrip() -> str:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as f:
            f.write(b"telecraft-uploads-live")
            path = Path(f.name)
        try:
            out = await client.uploads.upload_file(path, timeout=ctx.cfg.timeout)
            resource_ids["upload_file_type"] = type(out).__name__
            return f"upload_file={type(out).__name__}"
        finally:
            path.unlink(missing_ok=True)

    await run_step(
        name="uploads.upload_file",
        fn=step_uploads_upload_file_roundtrip,
        client=client,
        reporter=reporter,
        results=results,
    )

    await finalize_run(
        client=client,
        ctx=ctx,
        reporter=reporter,
        results=results,
        resource_ids=resource_ids,
    )


def test_uploads__upload_file__roundtrip_live(
    client_v2: Client,
    live_context: Any,
    audit_reporter: Any,
) -> None:
    asyncio.run(_run_uploads_suite(client_v2, live_context, audit_reporter))
