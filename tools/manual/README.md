# Manual Diagnostics

These scripts are optional operator diagnostics for local MTProto sessions. They are not part of
the library package API and are not required by CI.

Run them with the project virtualenv from the repository root, for example:

```bash
./.venv/bin/python tools/manual/smoke_get_me.py
```

Most scripts expect `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, and an existing session path or the
repo's default session discovery layout. They may connect to Telegram production, so treat them as
manual checks rather than deterministic tests.

Secrets and the account phone number are never accepted as command-line values. Login automation
may provide `TELEGRAM_PHONE`, `TELEGRAM_CODE`, and `TELEGRAM_PASSWORD`; otherwise the script
prompts, with 2FA input hidden. This keeps values out of `argv`, but environment variables may
still be readable by same-user processes. Populate them through a secret manager or protected
ignored file, and never put real values in inline shell assignments that can enter shell history.

`smoke_auth_key.py` never exports raw auth-key material. Its output is limited to public identifiers
and exchange diagnostics that are sufficient to confirm a successful handshake.
