# Sandbox Isolation (V1)

## Goal

Keep live QA isolated from production by default:
- runtime default is `sandbox`
- sandbox maps to Telegram `network=test`
- production access is opt-in and hard-gated

## Runtime Model

- `sandbox` runtime:
  - network: `test`
  - sessions: `.sessions/sandbox/`
  - audit peer file: `.sessions/sandbox/live_audit_peer.txt`
  - reports: `reports/live/sandbox/<run_id>/`
- `prod` runtime:
  - network: `prod`
  - sessions: `.sessions/prod/`
  - audit peer file: `.sessions/prod/live_audit_peer.txt`
  - reports: `reports/live/prod/<run_id>/`

## Production Override Rules

`apps/run.py`:
- required flag: `--allow-prod`
- required env: `TELECRAFT_ALLOW_PROD=1`

Live pytest (`tests/live`):
- required flag: `--allow-prod-live`
- required env: `TELECRAFT_ALLOW_PROD_LIVE=1`

If one of them is missing, execution is blocked with a concrete command example.

## Session Safety

Before connecting, the runtime checks that the selected session matches expected network:
- prod session loaded in sandbox runtime => blocked
- sandbox/test session loaded in prod runtime => blocked

This prevents accidental leakage caused by mixed session pointers.

## Migrating Existing Sessions

Dry-run:

```bash
./.venv/bin/python tools/migrate_sessions_layout.py --dry-run
```

Apply:

```bash
./.venv/bin/python tools/migrate_sessions_layout.py --apply
```

## Typical Sandbox Flow

1. Login in sandbox:

```bash
./.venv/bin/python apps/run.py login --runtime sandbox --dc 2
```

2. Run live core in sandbox:

```bash
./.venv/bin/python -m pytest tests/live/core -m live_core -vv -s \
  --run-live \
  --live-runtime sandbox \
  --live-destructive
```

3. Run optional safe lanes in sandbox:

```bash
./.venv/bin/python -m pytest tests/live/optional \
  -m "live_optional and not live_paid and not live_business and not live_chatlists and not live_stories_write and not live_channel_admin" \
  -vv -s \
  --run-live \
  --live-runtime sandbox
```

## Notes

- Telegram test environment is separate from production entities/history.
- Test data may be reset periodically; do not treat sandbox state as durable storage.
