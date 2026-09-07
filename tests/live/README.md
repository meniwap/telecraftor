# Live Tests

This folder contains the slim manual Telegram live smoke layer:

- `core/test_live_core_suite.py`
- `optional/test_live_prod_safe_baseline.py`
- `optional/test_live_unknown_constructor_recovery.py` (prod-safe synthetic recovery signal)
- `test_live_destructive_message_roundtrip.py` (separately gated; creates one temporary message)

Full commands and safety policy are documented in:

- `docs/11_live_runbook.md`
