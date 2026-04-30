# Public Beta Readiness Checklist

Internal planning file for agents. Not public docs.

Goal: prepare the first public `0.2.x` line without accidentally treating internal `0.1.x`
milestones as public releases.

## Release Line Policy

- `0.1.x`: internal milestones only
- `0.2.0aN`: public alpha
- `0.2.0bN`: public beta
- `0.2.0rcN`: release candidate
- `0.2.0`: first stable public line

## Required Before `0.2.0a1`

- `ruff` passes on `src tests tools apps`
- `mypy` passes on `src`
- `tests/meta` passes
- `pytest -m "not live"` passes
- `tests/live --collect-only` passes
- `python -m build` passes
- `CHANGELOG.md` has a `0.2.0a1` entry
- `pyproject.toml` version matches `0.2.0a1`
- `tools/release_check.py` passes for `--release-type alpha`

## Required Before `0.2.0b1`

- all alpha requirements
- production safe live gate passes:
  - `live_core_safe`
  - `live_prod_safe`
- `release_check.py` receives both prod-safe run IDs
- support policy and capability map are reviewed for public wording

## Required Before `0.2.0rc1`

- all beta requirements
- soak lane passes for at least 30 minutes
- no known receiver-loop/decode crash regressions
- public docs are internally consistent
- deprecated/experimental methods are clearly marked

## Required Before `0.2.0`

- all RC requirements
- final `prod_safe` live gate passes
- package build artifacts are checked
- release tag is created only after readiness artifacts pass

## Manual Gate Commands

Non-live:

```bash
PYTHONPATH=src ./.venv/bin/python -m ruff check src tests tools apps
PYTHONPATH=src ./.venv/bin/python -m mypy src
PYTHONPATH=src ./.venv/bin/python -m pytest tests/meta -q
PYTHONPATH=src ./.venv/bin/python -m pytest -m "not live" -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/live --collect-only -q
./.venv/bin/python -m build
```

Prod-safe:

```bash
TELECRAFT_ALLOW_PROD_LIVE=1 PYTHONPATH=src ./.venv/bin/python -m pytest \
  tests/live/core tests/live/optional \
  -m "live and (live_core_safe or live_prod_safe)" \
  -vv -s \
  --run-live \
  --allow-prod-live \
  --live-profile prod_safe \
  --live-audit-peer auto \
  --live-report-dir reports/live
```

Readiness check:

```bash
PYTHONPATH=src ./.venv/bin/python tools/release_check.py \
  --version 0.2.0b1 \
  --release-type beta \
  --prod-safe-run-core <run_id_core> \
  --prod-safe-run-baseline <run_id_baseline> \
  --write-dir reports/releases/0.2.0b1
```

## Stop Conditions

Do not publish/tag a public release when:

- any non-live gate fails
- prod-safe health probes fail
- soak run exposes repeated transport/decode failures
- release artifacts are missing
- changelog/version mismatch exists
- a stable breaking change lacks a deprecation entry
