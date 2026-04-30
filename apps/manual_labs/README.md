# Manual Labs

This directory contains manual, exploratory scripts for local development.

These scripts are not production demos and are not part of the production-readiness gates.
They may send real Telegram messages or exercise broad API flows, so run them only with an
active production session you control.

## Available Labs

- `test_new_features.py`: broad manual probe for newer client features.

## Run

From the repository root:

```bash
source apps/env.sh
TELECRAFT_ALLOW_PROD=1 ./.venv/bin/python apps/manual_labs/test_new_features.py
```

Required first-time setup:

```bash
TELECRAFT_ALLOW_PROD=1 ./.venv/bin/python apps/run.py login --runtime prod --allow-prod --dc 4
```
