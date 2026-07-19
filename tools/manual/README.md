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

`smoke_auth_key.py` never exports raw auth-key material. Its output is limited to public identifiers
and exchange diagnostics that are sufficient to confirm a successful handshake.
