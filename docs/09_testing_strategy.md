# Testing Strategy

## Deterministic Tests

- `tests/unit/client/v2/**`: public V2 wrapper contracts.
- `tests/unit/client/core/**`: client wiring, runtime-safety helpers, and tool contracts.
- `tests/unit/bot/**`: router, dispatcher, and event mapping behavior.
- `tests/unit/mtproto/**`: protocol-layer behavior without live network access.
- `tests/meta/**`: governance gates for versions, support policy, deprecations, and the V2
  method matrix.

Run the normal non-live gate with:

```bash
./.venv/bin/python -m ruff check src tests tools apps examples
./.venv/bin/python -m mypy src
./.venv/bin/python -m pytest tests/meta -q
./.venv/bin/python -m pytest -m "not live" -q
```

## Live Smoke Layer

`tests/live/**` is a small manual production smoke layer. It is intentionally not a broad Telegram
QA lab.

Kept files:

- `tests/live/core/test_live_core_suite.py`
- `tests/live/optional/test_live_prod_safe_baseline.py`
- `tests/live/_suite_shared.py`
- `tests/live/conftest.py`

The only supported live flags are:

- `--run-live`
- `--allow-prod-live`
- `--live-profile`
- `--live-report-dir`
- `--live-timeout`
- `--live-audit-peer`

Collect without touching Telegram:

```bash
./.venv/bin/python -m pytest tests/live --collect-only -q
```

Real live execution is manual, production-gated, and documented in `docs/11_live_runbook.md`.

## Governance

- Method support matrix: `tests/meta/v2_method_matrix.yaml`.
- Support contract: `tests/meta/v2_support_contract.json`.
- Deprecation registry: `tests/meta/v2_deprecations.json`.
- Matrix tiers are `unit`, `manual_live_optional`, `external_manual`, and
  `unsupported_or_experimental`.
- Name-based test coverage is enforced for `unit` rows only.
- Public `0.2.x+` releases require prod-safe live evidence; internal `0.1.x` milestones do not.
