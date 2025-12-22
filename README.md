# telecraft

Telegram client library (MTProto-first). Work in progress.

## Development

Create a virtualenv and install dev dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

Run checks:

```bash
python -m pytest
python -m ruff check src tests tools
python -m mypy src
```

Smoke-test auth key exchange (test DCs):

```bash
python tools/smoke_auth_key.py --dc 2 --framing intermediate --timeout 60 --out auth_key.json
```


