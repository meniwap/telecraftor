# Live QA Runbook

Live tests run manually against Telegram production sessions. They are never part of normal CI.

Production access is hard-gated by both:

- `--allow-prod-live`
- `TELECRAFT_ALLOW_PROD_LIVE=1`

Reports are written under `reports/live/prod/<run_id>/`. File artifacts are authoritative; Telegram
audit messages are best-effort and are only sent when `--live-audit-peer` is an explicit peer.
`--live-audit-peer auto` means file reports only.

## Prerequisites

- Valid prod session under `.sessions/prod/`.
- `TELEGRAM_API_ID` and `TELEGRAM_API_HASH`.
- `source apps/env.sh`, or export the same variables another way.

## Collect Only

This is the only live command safe for routine cleanup work:

```bash
./.venv/bin/python -m pytest tests/live --collect-only -q
```

## Prod-Safe Smoke

Run only with explicit approval:

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

Expected artifacts:

- `reports/live/prod/<run_id>/events.jsonl`
- `reports/live/prod/<run_id>/summary.md`
- `reports/live/prod/<run_id>/artifacts.json`

## Current Live Scope

The tracked live suite is limited to:

- core connection/profile/help/dialog read-only smoke
- broader prod-safe read-only baseline
- health probes around each step
- local JSONL/Markdown/JSON reports

It does not create groups/channels, use a second account, spend money, exercise admin moderation,
start calls, write stories, or run soak tests.

## Reading Results

Green:

- all steps `PASS`
- health probes pass
- `cleanup_errors=0`

Red:

- transport/decode/RPC failures
- failed health probe
- cleanup failure

## Troubleshooting

### `AUTH_KEY_DUPLICATED`

Telegram returns `AUTH_KEY_DUPLICATED` when the same MTProto auth key/session is detected from
another environment or otherwise invalidated by Telegram.

Treat this as a session hygiene issue, not a failed API assertion:

- stop any other process or repo using the copied session
- create a fresh production login with `apps/run.py login --allow-prod`
- keep the active pointer under `.sessions/prod/current`
- avoid using the same session file concurrently from multiple projects or machines
