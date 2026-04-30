# Reliability Soak Plan

Internal planning file for agents. Not public docs.

Goal: prove that Telecraft remains usable across longer production sessions without touching
paid/admin/second-account/destructive paths by default.

## Lane

- file: `tests/live/optional/test_live_prod_soak_suite.py`
- marker: `live_soak`
- required flag: `--live-soak`
- duration flag: `--live-soak-duration <seconds>`
- excluded from: CI, `pytest -m "not live"`, `prod_safe`

## Default Command

```bash
TELECRAFT_ALLOW_PROD_LIVE=1 PYTHONPATH=src ./.venv/bin/python -m pytest \
  tests/live/optional/test_live_prod_soak_suite.py \
  -m "live_soak" \
  -vv -s \
  --run-live \
  --allow-prod-live \
  --live-soak \
  --live-soak-duration 900 \
  --live-audit-peer auto \
  --live-report-dir reports/live
```

## What It Checks

Each iteration performs read-only calls:

- `profile.me`
- `dialogs.list(limit=1)`
- `help.config`

The suite records:

- iteration count
- elapsed duration
- result type per health path
- standard live artifacts: `events.jsonl`, `summary.md`, `artifacts.json`

## Promotion Targets

- 15 minutes: regular manual reliability check
- 30 minutes: beta candidate check
- 60 minutes: release-candidate confidence check

## Green / Yellow / Red

- Green: all iterations pass, artifacts are complete, cleanup errors are zero
- Yellow: isolated Telegram timeout/flood condition; rerun once before classifying
- Red: transport/decode crash, receiver loop failure, repeated timeout, or missing artifacts

## Not Covered

This is intentionally not a full stress test. It does not cover:

- second-account/admin flows
- paid paths
- destructive cleanup
- update-loop high-volume behavior

Those require separate manual lanes.
