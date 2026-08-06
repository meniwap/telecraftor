from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


class _FakeProfileAPI:
    def __init__(self, *, error: Exception | None = None) -> None:
        self._error = error

    async def me(self, *, timeout: float = 20.0):
        _ = timeout
        if self._error is not None:
            raise self._error
        return SimpleNamespace(id=12345)


class _FakeClient:
    def __init__(
        self,
        *,
        profile_error: Exception | None = None,
        close_error: Exception | None = None,
    ) -> None:
        self.profile = _FakeProfileAPI(error=profile_error)
        self._close_error = close_error

    async def close(self) -> None:
        if self._close_error is not None:
            raise self._close_error
        return None


class _FakeReporter:
    def __init__(self, *, live_profile: str = "prod_safe", timeout: float = 5.0) -> None:
        self.events: list[dict[str, object]] = []
        self.ctx = SimpleNamespace(
            cfg=SimpleNamespace(live_profile=live_profile, timeout=timeout),
            artifacts={},
        )

    async def emit(self, **kwargs):
        self.events.append(kwargs)

    async def close(self) -> None:
        return None


def test_run_step__redacts_credentials_from_failure_details() -> None:
    from tests.live import _suite_shared as shared

    api_id = 987654321
    api_hash = "synthetic-api-hash"
    results: list[shared.StepResult] = []
    reporter = _FakeReporter(live_profile="default")
    reporter.ctx.redact = (
        lambda value: str(value)
        .replace(api_hash, "<redacted>")
        .replace(
            str(api_id),
            "<redacted>",
        )
    )

    async def _step() -> str:
        raise RuntimeError(f"failed with {api_id} and {api_hash}")

    asyncio.run(
        shared.run_step(
            name="redaction.fail",
            fn=_step,
            client=_FakeClient(),  # type: ignore[arg-type]
            reporter=reporter,
            results=results,
        )
    )

    assert len(results) == 1
    assert results[0].details == "RuntimeError: failed with <redacted> and <redacted>"
    assert reporter.events[-1]["details"] == results[0].details


def test_run_step__prod_safe__records_health_probe_pass() -> None:
    from tests.live import _suite_shared as shared

    results: list[shared.StepResult] = []
    reporter = _FakeReporter(live_profile="prod_safe")
    client = _FakeClient()

    async def _step() -> str:
        return "ok"

    asyncio.run(
        shared.run_step(
            name="probe.pass",
            fn=_step,
            client=client,  # type: ignore[arg-type]
            reporter=reporter,
            results=results,
        )
    )

    assert len(results) == 1
    assert results[0].status == "PASS"
    assert results[0].health_probe is not None
    probes = reporter.ctx.artifacts["connection_health_probes"]
    assert probes["enabled"] is True
    assert probes["pass"] == 1
    assert probes["fail"] == 0
    assert [e["status"] for e in reporter.events] == ["START", "PASS"]


def test_run_step__destructive_message__records_health_probe_pass() -> None:
    from tests.live import _suite_shared as shared

    results: list[shared.StepResult] = []
    reporter = _FakeReporter(live_profile="destructive_message")

    async def _step() -> str:
        return "ok"

    asyncio.run(
        shared.run_step(
            name="probe.destructive",
            fn=_step,
            client=_FakeClient(),  # type: ignore[arg-type]
            reporter=reporter,
            results=results,
        )
    )

    assert results[0].status == "PASS"
    assert results[0].health_probe == "PASS: profile.me id=12345"
    assert reporter.ctx.artifacts["connection_health_probes"]["pass"] == 1


def test_run_step__prod_safe__classifies_health_probe_failure_as_fail_health() -> None:
    from tests.live import _suite_shared as shared

    results: list[shared.StepResult] = []
    reporter = _FakeReporter(live_profile="prod_safe")
    client = _FakeClient(profile_error=asyncio.TimeoutError())

    async def _step() -> str:
        return "ok"

    asyncio.run(
        shared.run_step(
            name="probe.fail",
            fn=_step,
            client=client,  # type: ignore[arg-type]
            reporter=reporter,
            results=results,
        )
    )

    assert len(results) == 1
    assert results[0].status == "FAIL_HEALTH"
    assert results[0].error_class == "timeout"
    probes = reporter.ctx.artifacts["connection_health_probes"]
    assert probes["pass"] == 0
    assert probes["fail"] == 1
    assert [e["status"] for e in reporter.events] == ["START", "FAIL_HEALTH"]
    assert reporter.events[-1]["error_class"] == "timeout"


def test_error_classification__maps_timeout_rpc_transport_decode() -> None:
    from tests.live import _suite_shared as shared

    assert shared.classify_live_error(asyncio.TimeoutError()) == "timeout"
    assert shared.classify_live_error(ConnectionError("connection reset by peer")) == "transport"
    assert shared.classify_live_error(RuntimeError("Unknown constructor id: 123")) == "decode"
    assert shared.classify_live_error(RuntimeError("RPC_ERROR 400: METHOD_INVALID")) == "capability"
    assert shared.classify_live_error(RuntimeError("RPC_ERROR 400: CHAT_WRITE_FORBIDDEN")) == "rpc"


def test_finalize_run__writes_numeric_cleanup_error_count(tmp_path: Path) -> None:
    from tests.live import _suite_shared as shared

    class _Context:
        run_id = "run-1"
        run_dir = tmp_path
        source_commit = "a" * 40
        source_tree_clean = True
        cfg = SimpleNamespace(timeout=1.0)
        artifacts = {
            "connection_health_probes": {
                "enabled": True,
                "probe": "profile.me",
                "pass": 1,
                "fail": 0,
            }
        }

        async def run_cleanups(self) -> list[str]:
            return []

    ctx = _Context()
    reporter = _FakeReporter()
    reporter.ctx = ctx
    result = asyncio.run(
        shared.finalize_run(
            client=_FakeClient(),  # type: ignore[arg-type]
            ctx=ctx,
            reporter=reporter,
            results=[shared.StepResult(name="identity.profile", status="PASS", details="ok")],
            resource_ids={},
        )
    )

    artifact = json.loads((tmp_path / "artifacts.json").read_text(encoding="utf-8"))
    assert artifact["cleanup_errors"] == 0
    assert isinstance(artifact["cleanup_errors"], int)
    assert result["cleanup_errors"] == 0


def test_finalize_run__recursively_redacts_credentials_from_raw_reports(tmp_path: Path) -> None:
    from tests.live import _suite_shared as shared

    api_id = 987654321
    api_hash = "synthetic-api-hash"

    class _Context:
        run_id = "run-redacted"
        run_dir = tmp_path
        source_commit = "a" * 40
        source_tree_clean = True
        cfg = SimpleNamespace(timeout=1.0)
        artifacts = {
            "connection_health_probes": {
                "enabled": True,
                "probe": "profile.me",
                "pass": 1,
                "fail": 0,
            }
        }

        def redact(self, value: object) -> str:
            return (
                str(value)
                .replace(api_hash, "<redacted>")
                .replace(
                    str(api_id),
                    "<redacted>",
                )
            )

        async def run_cleanups(self) -> list[str]:
            return [f"cleanup exposed {api_hash}"]

    ctx = _Context()
    reporter = _FakeReporter()
    reporter.ctx = ctx
    with pytest.raises(AssertionError, match="1 cleanup errors"):
        asyncio.run(
            shared.finalize_run(
                client=_FakeClient(),  # type: ignore[arg-type]
                ctx=ctx,
                reporter=reporter,
                results=[
                    shared.StepResult(
                        name="identity.profile",
                        status="PASS",
                        details=f"configured={api_id}",
                    )
                ],
                resource_ids={
                    "configured_api_id": api_id,
                    "nested": {"configured_api_hash": api_hash},
                    "sequence": [api_id, api_hash],
                },
            )
        )

    artifacts_text = (tmp_path / "artifacts.json").read_text(encoding="utf-8")
    summary_text = (tmp_path / "summary.md").read_text(encoding="utf-8")
    event_text = json.dumps(
        [
            {key: value for key, value in event.items() if key != "client"}
            for event in reporter.events
        ],
        ensure_ascii=False,
    )
    for rendered in (artifacts_text, summary_text, event_text):
        assert str(api_id) not in rendered
        assert api_hash not in rendered
    artifacts = json.loads(artifacts_text)
    assert artifacts["resources"]["configured_api_id"] == "<redacted>"
    assert artifacts["resources"]["nested"]["configured_api_hash"] == "<redacted>"


def test_finalize_run__client_close_failure_blocks_release_evidence(tmp_path: Path) -> None:
    from tests.live import _suite_shared as shared

    class _Context:
        run_id = "run-close-failure"
        run_dir = tmp_path
        source_commit = "a" * 40
        source_tree_clean = True
        cfg = SimpleNamespace(timeout=1.0)
        artifacts = {
            "connection_health_probes": {
                "enabled": True,
                "probe": "profile.me",
                "pass": 1,
                "fail": 0,
            }
        }

        async def run_cleanups(self) -> list[str]:
            return []

    ctx = _Context()
    reporter = _FakeReporter()
    reporter.ctx = ctx
    with pytest.raises(AssertionError, match="1 cleanup errors"):
        asyncio.run(
            shared.finalize_run(
                client=_FakeClient(close_error=OSError("persist failed")),  # type: ignore[arg-type]
                ctx=ctx,
                reporter=reporter,
                results=[shared.StepResult(name="identity.profile", status="PASS", details="ok")],
                resource_ids={},
            )
        )

    artifact = json.loads((tmp_path / "artifacts.json").read_text(encoding="utf-8"))
    assert artifact["cleanup_errors"] == 1
    assert "client.close: OSError" in (tmp_path / "summary.md").read_text(encoding="utf-8")
