# Live Tests

This folder contains manual Telegram live lanes:

- `core/`
- `second_account/`
- `optional/`

Full commands and safety policy are documented in:

- `docs/11_live_runbook.md`

## Note (Sandbox Test Accounts)

As of **February 10, 2026**, sandbox login on Telegram test network (`DC 2`, `149.154.167.40:443`)
may fail with `PHONE_CODE_INVALID` even when `sendCode` succeeds.

Treat this as a temporary test-network/account-policy issue and follow the runbook for safe prod
validation until sandbox auth behavior is stable again.
