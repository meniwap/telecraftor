# Live QA Runbook

Live tests run manually against Telegram production sessions. They are never part of normal CI.

Production access is hard-gated by both:

- `--allow-prod-live`
- `TELECRAFT_ALLOW_PROD_LIVE=1`

Reports are written under `reports/live/prod/<run_id>/`. File artifacts are authoritative.
`prod_safe` and `destructive_message` always use file-only reporting, even if an audit peer is
provided. Only the `default` profile may send best-effort Telegram audit messages when
`--live-audit-peer` is an explicit peer; `auto` means file reports only.

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

The prod-safe selection also runs a bounded recovery-fault smoke outside the two reported release
step lists. It starts the updates engine, injects an in-memory structured recovery signal (never a
malformed network payload or replayed RPC), and requires a real replacement TCP connection, a new
MTProto session ID, layer initialization, `getDifference`, and a healthy resumed update stream.
Its local `updateConfig` health sentinel intentionally has no `pts/qts/seq/channel_pts`; the smoke
therefore also requires the unknown-constructor circuit to remain armed until a later independent
cursor-bearing live update is decoded, delivered, and persisted. A final `profile.me` proves the
replacement sender remains RPC-healthy while that conservative circuit state is retained.
It performs no Telegram write and does not change the core/baseline run IDs consumed by
`tools/release_check.py`. The fault smoke intentionally creates no reporter directory or release
artifact. To run only that extra smoke, keep the same production gates and select its path:

```bash
TELECRAFT_ALLOW_PROD_LIVE=1 ./.venv/bin/python -m pytest \
  tests/live/optional/test_live_unknown_constructor_recovery.py \
  -vv -s --run-live --allow-prod-live --live-profile prod_safe
```

These raw reports include step and exception details plus account/peer identifiers. The live
reporter redacts the configured Telegram API ID and hash, but it is not a general-purpose scrubber
for message content or personal data. Treat all three files as sensitive local artifacts: never
commit them, upload them as CI artifacts, or share them without a separate review and redaction.

## Destructive Message Round-Trip

This is a separate, explicitly approved check. It is not enabled by `prod_safe`. Both peer values
must be set to the approved target and must match after normalizing case and an optional leading
`@`.

```bash
TELECRAFT_ALLOW_PROD_LIVE=1 \
TELECRAFT_ALLOW_DESTRUCTIVE_LIVE=1 \
TELECRAFT_DESTRUCTIVE_PEER=@approved_test_peer \
./.venv/bin/python -m pytest tests/live/test_live_destructive_message_roundtrip.py \
  -m "live and live_destructive" \
  -vv -s \
  --run-live \
  --allow-prod-live \
  --live-profile destructive_message \
  --allow-destructive-live \
  --live-destructive-peer @approved_test_peer \
  --live-audit-peer auto \
  --live-report-dir reports/live
```

All gates are required: the production CLI/environment pair, the destructive
CLI/environment pair, matching CLI/environment peers, the `destructive_message` profile, and
file-only audit mode. The source tree must also be clean.

The test starts the MTProto updates engine before writing, creates exactly one uniquely tagged text
message, and observes that exact message through the bounded live update path. If Telegram returns
the originating update only in the RPC result, the test performs one bounded update-engine restart
to force authoritative `getDifference` catch-up from the pre-send checkpoint. It then verifies the
initial text, edits it, and verifies the edited text. Revoke cleanup is registered before the send
attempt and runs in `finally`; if a send times out after Telegram may have accepted it, cleanup
searches only for the unique token and exact test text. A cleanup failure fails the run and leaves
the token and peer in the local report for manual recovery. It does not retry the send or delete
messages that do not exactly match the test-created resource. Update assertions do not render or
persist message bodies; raw local reports remain sensitive under the policy above.

## Current Live Scope

The tracked live suite is limited to:

- core connection/profile/help/dialog read-only smoke
- broader prod-safe read-only baseline
- health probes around each step
- local JSONL/Markdown/JSON reports
- bounded synthetic unknown-constructor recovery over a real replacement connection
- one separately gated send/read/edit/read/revoke round-trip against an explicitly approved peer

Outside that one temporary message, it does not create groups/channels, use a second account,
spend money, exercise admin moderation, start calls, write stories, or run soak tests.

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
