# Live QA Runbook

## Purpose

Run Telegram live tests in explicit lanes:
- `core`: no second account required
- `second_account`: add/remove flow for `@meniwap`
- `optional`: unstable/expensive flows (dialogs/stickers/topics/privacy+notifications/games/saved/stars/gifts/stories readonly)
- `paid`: optional spending-capable gifts/stars flow
- `business`: business API smoke flow (opt-in)
- `chatlists`: chatlists API smoke flow (opt-in)
- `calls`: calls readonly smoke flow (opt-in)
- `calls_write`: calls write/destructive smoke flow (opt-in)
- `takeout`: takeout smoke flow (opt-in)
- `webapps`: webapps smoke flow (opt-in)
- `admin`: admin-sensitive smoke flows (opt-in)
- `premium`: premium boosts smoke flow (opt-in)
- `sponsored`: sponsored/channel-flood smoke flow (opt-in)
- `passkeys`: passkeys smoke flow (opt-in)
- `account_music`: account music + gift themes readonly smoke flow
- `stories_write`: stories write smoke flow (opt-in)
- `channel_admin`: channel admin smoke flow (opt-in)
- `bot`: bot-session E2E smoke flow (opt-in)
- dual audit output (Telegram + local files)

## Prerequisites

- Valid session file under `.sessions/sandbox/` (default runtime) or `.sessions/prod/`
- `TELEGRAM_API_ID` and `TELEGRAM_API_HASH` in env
- Optional: `TELEGRAM_SESSION_PATH`

## Known Issue (Sandbox Login)

As of **February 10, 2026**, sandbox login to Telegram test network (`DC 2`, `149.154.167.40:443`)
may fail with:

- `RPC_ERROR 400: PHONE_CODE_INVALID` after `sendCode` succeeds

Notes:
- This issue was reproduced with clean sandbox sessions and multiple new `999662YYYY` numbers.
- The same behavior was observed with both Telecraft and a Telethon cross-check, which suggests
  the issue is likely test-network-side/account-policy-side rather than a Telecraft runtime issue.
- Until it is resolved, use production live checks only with explicit prod overrides and safe lanes.

## TL Decode Forensics (Optional)

If a live lane hits an unknown/new TL constructor, you can capture raw failing payloads:

```bash
TELECRAFT_DEBUG_DUMP_TL=1 \
TELECRAFT_DEBUG_TL_DIR=reports/debug_tl \
python -m pytest tests/live/optional/test_live_optional_polls.py -vv -s \
  --run-live \
  --live-runtime sandbox \
  --live-enable-polls
```

Notes:
- Decoder now keeps the receiver loop alive on decode failures and fails only relevant requests.
- Dump files are written only when `TELECRAFT_DEBUG_DUMP_TL=1` is set.

## Command

Core lane:

```bash
python -m pytest tests/live/core -m "live_core" -vv -s \
  --run-live \
  --live-runtime sandbox \
  --live-destructive \
  --live-audit-peer auto \
  --live-report-dir reports/live
```

Second-account lane (explicit):

```bash
python -m pytest tests/live/second_account -m "live_second_account" -vv -s \
  --run-live \
  --live-runtime sandbox \
  --live-destructive \
  --live-second-account meniwap \
  --live-audit-peer auto \
  --live-report-dir reports/live
```

Optional polls lane:

```bash
python -m pytest tests/live/optional -m "live_optional" -vv -s \
  --run-live \
  --live-runtime sandbox \
  --live-enable-polls
```

Safe non-paid optional baseline:

```bash
python -m pytest tests/live/optional \
  -m "live_optional and not live_paid and not live_business and not live_chatlists and not live_stories_write and not live_channel_admin" \
  -vv -s \
  --run-live \
  --live-runtime sandbox \
  --live-audit-peer auto \
  --live-report-dir reports/live
```

Strict polls close mode (optional):

```bash
python -m pytest tests/live/optional/test_live_optional_polls.py -vv -s \
  --run-live \
  --live-runtime sandbox \
  --live-enable-polls \
  --live-strict-polls-close \
  --live-audit-peer auto \
  --live-report-dir reports/live
```

Optional paid lane:

```bash
python -m pytest tests/live/optional/test_live_gifts_paid.py -vv -s \
  --run-live \
  --live-runtime sandbox \
  --live-paid
```

Optional business lane:

```bash
python -m pytest tests/live/optional/test_live_business_suite.py -vv -s \
  --run-live \
  --live-runtime sandbox \
  --live-business
```

Optional chatlists lane:

```bash
python -m pytest tests/live/optional/test_live_chatlists_suite.py -vv -s \
  --run-live \
  --live-runtime sandbox \
  --live-chatlists
```

Optional calls readonly lane:

```bash
python -m pytest tests/live/optional/test_live_calls_readonly_suite.py -vv -s \
  --run-live \
  --live-runtime sandbox \
  --live-calls
```

Optional calls write lane:

```bash
python -m pytest tests/live/optional/test_live_calls_write_suite.py -vv -s \
  --run-live \
  --live-runtime sandbox \
  --live-calls-write \
  --live-destructive
```

Required env for calls lanes:
- `TELECRAFT_LIVE_CALLS_PEER` (readonly lane)
- `TELECRAFT_LIVE_CALLS_WRITE_PEER` (write lane)

Optional takeout lane:

```bash
python -m pytest tests/live/optional/test_live_takeout_suite.py -vv -s \
  --run-live \
  --live-runtime sandbox \
  --live-takeout
```

Optional webapps lane:

```bash
python -m pytest tests/live/optional/test_live_webapps_suite.py -vv -s \
  --run-live \
  --live-runtime sandbox \
  --live-webapps
```

Required env for webapps lane:
- `TELECRAFT_LIVE_WEBAPP_BOT` (bot peer, e.g. `@mybot`)

Optional premium lane:

```bash
python -m pytest tests/live/optional/test_live_premium_boosts_readonly_suite.py -vv -s \
  --run-live \
  --live-runtime sandbox \
  --live-premium
```

Optional sponsored lane:

```bash
python -m pytest tests/live/optional/test_live_channels_sponsored_suite.py -vv -s \
  --run-live \
  --live-runtime sandbox \
  --live-sponsored \
  --live-admin
```

Optional passkeys lane:

```bash
python -m pytest tests/live/optional/test_live_passkeys_suite.py -vv -s \
  --run-live \
  --live-runtime sandbox \
  --live-passkeys
```

Optional account music readonly lane:

```bash
python -m pytest tests/live/optional/test_live_account_music_readonly_suite.py -vv -s \
  --run-live \
  --live-runtime sandbox
```

Optional announcements readonly lane:

```bash
python -m pytest tests/live/optional/test_live_messages_announcements_suite.py -vv -s \
  --run-live \
  --live-runtime sandbox
```

Optional contacts requirements lane:

```bash
python -m pytest tests/live/optional/test_live_contacts_requirements_suite.py -vv -s \
  --run-live \
  --live-runtime sandbox
```

Optional conference-chain readonly lane:

```bash
python -m pytest tests/live/optional/test_live_calls_conference_chain_suite.py -vv -s \
  --run-live \
  --live-runtime sandbox \
  --live-calls
```

Required env for conference-chain lane:
- `TELECRAFT_LIVE_GROUP_CALL_ID`
- `TELECRAFT_LIVE_GROUP_CALL_ACCESS_HASH`
- `TELECRAFT_LIVE_GROUP_CALL_SUB_CHAIN_ID`

Optional admin-sensitive lanes:

```bash
python -m pytest tests/live/optional/test_live_stats_readonly_suite.py -vv -s \
  --run-live \
  --live-runtime sandbox \
  --live-admin
```

Required env for chatlists lane:
- `TELECRAFT_LIVE_CHATLIST_SLUG` with a valid invite slug (no `https://t.me/addlist/` prefix)

Optional stories write lane:

```bash
python -m pytest tests/live/optional/test_live_stories_write_suite.py -vv -s \
  --run-live \
  --live-runtime sandbox \
  --live-stories-write
```

Optional channel admin lane:

```bash
python -m pytest tests/live/optional/test_live_channels_admin_suite.py -vv -s \
  --run-live \
  --live-runtime sandbox \
  --live-channel-admin
```

Optional bot lane:

```bash
python -m pytest tests/live/bot -m "live_bot" -vv -s \
  --run-live \
  --live-runtime sandbox \
  --live-bot
```

Required env for bot lane:
- `TELECRAFT_LIVE_BOT_TEST_PEER` (peer where both user+bot can post/read, e.g. `@your_group`)
- optional: `TELEGRAM_BOT_SESSION_PATH` (defaults to `.sessions/<runtime>/current_bot` resolution)

Prod override (explicit, hard-gated):

```bash
TELECRAFT_ALLOW_PROD_LIVE=1 python -m pytest tests/live/core -m "live_core" -vv -s \
  --run-live \
  --live-runtime prod \
  --allow-prod-live \
  --live-destructive
```

Note: pass `--live-second-account` without `@` because pytest treats leading `@` specially.
The fixture normalizes bare usernames to `@username`.

## Outputs

For each run (`run_id`):
- `reports/live/sandbox/<run_id>/events.jsonl` (sandbox runtime)
- `reports/live/sandbox/<run_id>/summary.md`
- `reports/live/sandbox/<run_id>/artifacts.json`
- `reports/live/prod/<run_id>/...` (prod runtime)

If `--live-audit-peer auto` is used, a persistent audit destination is created and stored in:
- `.sessions/sandbox/live_audit_peer.txt` (sandbox runtime)
- `.sessions/prod/live_audit_peer.txt` (prod runtime)

## Safety Rules

- Always run with `--run-live`.
- Default live runtime is sandbox (`--live-runtime sandbox`).
- Prod live requires both `--allow-prod-live` and `TELECRAFT_ALLOW_PROD_LIVE=1`.
- Destructive operations require `--live-destructive`.
- `second_account` lane requires explicit `--live-second-account`.
- `paid` lane requires explicit `--live-paid`.
- `business` lane requires explicit `--live-business`.
- `chatlists` lane requires explicit `--live-chatlists`.
- `calls` readonly lane requires explicit `--live-calls`.
- `calls_write` lane requires explicit `--live-calls-write`.
- `takeout` lane requires explicit `--live-takeout`.
- `webapps` lane requires explicit `--live-webapps`.
- `admin` sensitive lanes require explicit `--live-admin`.
- `premium` lane requires explicit `--live-premium`.
- `sponsored` lane requires explicit `--live-sponsored` (and `--live-admin` for admin-bound actions).
- `passkeys` lane requires explicit `--live-passkeys`.
- `stories_write` lane requires explicit `--live-stories-write`.
- `channel_admin` lane requires explicit `--live-channel-admin`.
- `bot` lane requires explicit `--live-bot`.
- `business` and `chatlists` suites are fail-fast on unsupported/account capability errors.
- `polls` close is warning-only by default; use `--live-strict-polls-close` to fail on close errors.
- Cleanup runs even on failed steps.
