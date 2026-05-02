# Release Process

This document defines the manual process for Telecraft release readiness.
The first public beta is GitHub-only; do not publish to PyPI in this line unless a later release
plan explicitly adds that step.

## Release Lines

- `0.1.x`: internal milestones; live artifacts are optional.
- `0.2.x+`: public line; prod-safe live evidence is required.

## Internal 0.1.x Gate

```bash
./.venv/bin/python tools/check_repo_hygiene.py
./.venv/bin/python -m ruff check src tests tools apps examples
./.venv/bin/python -m mypy src
./.venv/bin/python -m pytest tests/meta -q
./.venv/bin/python -m pytest -m "not live" -q
./.venv/bin/python -m pytest tests/live --collect-only -q
./.venv/bin/python -m build
./.venv/bin/python tools/check_repo_hygiene.py --artifacts
```

## Public 0.2.x+ Gate

Public releases require the internal gate plus manually approved prod-safe live evidence:

```bash
TELECRAFT_ALLOW_PROD_LIVE=1 ./.venv/bin/python -m pytest tests/live \
  -m "live and live_prod_safe" \
  -vv -s \
  --run-live \
  --allow-prod-live \
  --live-profile prod_safe \
  --live-audit-peer auto \
  --live-report-dir reports/live
```

Record the run IDs for the core smoke and baseline artifacts, then validate:

```bash
./.venv/bin/python tools/release_check.py \
  --version 0.2.0b1 \
  --release-type beta \
  --prod-safe-run-core <run_id_core> \
  --prod-safe-run-baseline <run_id_baseline> \
  --write-dir reports/releases/0.2.0b1
```

`tools/release_check.py` always validates version, changelog, support contract, and deprecations.
It requires live artifact IDs only for public `0.2.x+` release lines.

## GitHub Beta Release

After all gates pass:

```bash
git tag v0.2.0b1
git push origin v0.2.0b1
```

Create a GitHub prerelease using the changelog entry and include that this beta is MTProto-only,
with no HTTP Bot API module.

## Abort Rules

Abort the release if any gate fails, if the changelog/version mismatch, or if
`tools/release_check.py` reports blockers. Do not tag a release until readiness is green.
