# Live QA Runbook (Production Only)

## Purpose

Live tests run manually against Telegram production sessions. They are never part of normal CI.

Default production access is hard-gated:
- `--allow-prod-live`
- `TELECRAFT_ALLOW_PROD_LIVE=1`

Reports are written under `reports/live/prod/<run_id>/`.
Audit peer is stored at `.sessions/prod/live_audit_peer.txt`.

## Prerequisites

- Valid prod session under `.sessions/prod/`
- `TELEGRAM_API_ID` and `TELEGRAM_API_HASH`
- `source apps/env.sh`

## Production Safe Reliability Gate

Use this before public releases and for regular confidence checks:

```bash
TELECRAFT_ALLOW_PROD_LIVE=1 python -m pytest tests/live/core tests/live/optional \
  -m "live and (live_core_safe or live_prod_safe)" \
  -vv -s \
  --run-live \
  --allow-prod-live \
  --live-profile prod_safe \
  --live-audit-peer auto \
  --live-report-dir reports/live
```

Expected artifacts:
- `reports/live/prod/<run_id>/events.jsonl`
- `reports/live/prod/<run_id>/summary.md`
- `reports/live/prod/<run_id>/artifacts.json`

## Core Lane

Safe subset:

```bash
TELECRAFT_ALLOW_PROD_LIVE=1 python -m pytest tests/live/core -m "live_core_safe" -vv -s \
  --run-live \
  --allow-prod-live \
  --live-profile prod_safe \
  --live-audit-peer auto \
  --live-report-dir reports/live
```

Destructive subset:

```bash
TELECRAFT_ALLOW_PROD_LIVE=1 python -m pytest tests/live/core -m "live_core_destructive" -vv -s \
  --run-live \
  --allow-prod-live \
  --live-destructive \
  --live-audit-peer auto \
  --live-report-dir reports/live
```

## Optional Lanes

Run all optional lanes with their own explicit flags only when needed:

```bash
TELECRAFT_ALLOW_PROD_LIVE=1 python -m pytest tests/live/optional -m "live_optional" -vv -s \
  --run-live \
  --allow-prod-live \
  --live-audit-peer auto \
  --live-report-dir reports/live
```

Sensitive flags:
- `--live-paid`
- `--live-business`
- `--live-chatlists`
- `--live-calls`
- `--live-calls-write`
- `--live-takeout`
- `--live-webapps`
- `--live-admin`
- `--live-stories-write`
- `--live-channel-admin`
- `--live-premium`
- `--live-sponsored`
- `--live-passkeys`
- `--live-soak`

## Second Account Lane

This lane is isolated and requires explicit opt-in:

```bash
TELECRAFT_ALLOW_PROD_LIVE=1 python -m pytest tests/live/second_account -m "live_second_account" -vv -s \
  --run-live \
  --allow-prod-live \
  --live-destructive \
  --live-second-account second_account_username \
  --live-audit-peer auto \
  --live-report-dir reports/live
```

Pass the username without `@` because pytest treats leading `@` as a response-file marker.

## Second Account Admin Hardening Lane

This lane verifies promote/demote and ban/unban/kick rollback behavior. It is destructive,
excluded from `prod_safe`, and requires explicit admin opt-in:

```bash
TELECRAFT_ALLOW_PROD_LIVE=1 python -m pytest \
  tests/live/second_account/test_live_admin_moderation_second_account.py \
  -m "live_second_account and live_admin" \
  -vv -s \
  --run-live \
  --allow-prod-live \
  --live-destructive \
  --live-admin \
  --live-second-account second_account_username \
  --live-audit-peer auto \
  --live-report-dir reports/live
```

Expected behavior:
- temporary megagroup/channel is created
- second account is added, promoted, demoted, banned, unbanned, kicked, and unbanned again
- cleanup demotes/unbans the second account and deletes the temporary group
- `cleanup_errors=0` in `artifacts.json`

## Soak / Reliability Lane

Use this manually to prove longer-running read stability. It does not run in `prod_safe`
because it is intentionally slower:

```bash
TELECRAFT_ALLOW_PROD_LIVE=1 python -m pytest \
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

The soak loop repeatedly exercises read-only health paths:
- `profile.me`
- `dialogs.list(limit=1)`
- `help.config`

Start with 15 minutes (`900` seconds), then increase to 30-60 minutes for release candidates.

## Reading Results

Green:
- all steps `PASS`
- health probes pass
- `cleanup_errors=0`

Red:
- transport/decode/RPC failures
- failed health probe
- cleanup failure on destructive lanes

File artifacts are authoritative; Telegram audit messages are best-effort.

## Troubleshooting

### `AUTH_KEY_DUPLICATED`

Telegram returns `AUTH_KEY_DUPLICATED` when the same MTProto auth key/session is detected
from another environment or otherwise invalidated by Telegram.

Treat this as a session hygiene issue, not a failed API assertion:
- stop any other process/repo using the copied session
- create a fresh production login with `apps/run.py login --allow-prod`
- keep the active pointer under `.sessions/prod/current`
- avoid using the same session file concurrently from multiple projects or machines
