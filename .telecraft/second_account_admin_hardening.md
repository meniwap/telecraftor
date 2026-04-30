# Second Account / Admin Hardening Playbook

Internal planning file for agents. Not public docs.

Goal: verify admin and membership flows with rollback guarantees, without running them by default.

## Required Opt-In

Run only with all of these:

```bash
TELECRAFT_ALLOW_PROD_LIVE=1 PYTHONPATH=src ./.venv/bin/python -m pytest \
  tests/live/second_account \
  -m "live_second_account" \
  -vv -s \
  --run-live \
  --allow-prod-live \
  --live-destructive \
  --live-admin \
  --live-second-account <bare_username_or_user_ref> \
  --live-audit-peer auto \
  --live-report-dir reports/live
```

Use a bare username without `@` because pytest treats leading `@` as response-file syntax.

## Coverage

- membership add/remove
- cleanup-on-failure for add/remove
- promote/demote rollback
- ban/unban rollback
- kick + final unban rollback

## Cleanup Guarantees

Every destructive run must:

- create a temporary megagroup/channel
- register cleanup for second-user state before deleting the group
- demote the second account before group deletion
- unban/unrestrict the second account before group deletion
- delete the temporary group/channel
- emit `events.jsonl`, `summary.md`, and `artifacts.json`
- finish with `cleanup_errors=0`

## Not Run By Default

This lane is excluded from:

- normal CI
- `pytest -m "not live"`
- prod-safe live profile
- optional live baseline

## Manual Classification

- Green: all steps pass, `cleanup_errors=0`
- Yellow: Telegram privacy/capability prevents adding the second account; review manually
- Red: admin rollback failure, cleanup failure, transport/decode failure, or unresolved temp group
