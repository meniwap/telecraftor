from __future__ import annotations

import asyncio
from types import SimpleNamespace


class _FakeProfileAPI:
    def __init__(self, *, error: Exception | None = None) -> None:
        self._error = error

    async def me(self, *, timeout: float = 20.0):
        _ = timeout
        if self._error is not None:
            raise self._error
        return SimpleNamespace(id=12345)


class _FakeClient:
    def __init__(self, *, profile_error: Exception | None = None) -> None:
        self.profile = _FakeProfileAPI(error=profile_error)


class _FakeReporter:
    def __init__(self, *, live_profile: str = "prod_safe", timeout: float = 5.0) -> None:
        self.events: list[dict[str, object]] = []
        self.ctx = SimpleNamespace(
            cfg=SimpleNamespace(live_profile=live_profile, timeout=timeout),
            artifacts={},
        )

    async def emit(self, **kwargs):
        self.events.append(kwargs)


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
