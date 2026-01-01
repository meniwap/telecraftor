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

## Client: peer resolution (userbot-friendly)

`telecraft` is MTProto-first and async-only. For userbots you typically want to target peers by:
- `@username` (resolve on-demand)
- `+phone` (resolve on-demand)
- cached numeric IDs (after priming / past interactions)

High-level helpers:

```python
from telecraft.client import MtprotoClient, Peer

# ...
# await client.send_message("@username", "hi")
# await client.send_message(Peer.channel(123456), "hi")
```

## Bot runner (stable userbots)

Use `telecraft.bot.run_userbot()` to run a Router/Dispatcher with reconnect/backoff.

Smoke-test auth key exchange (test DCs):

```bash
python tools/smoke_auth_key.py --dc 2 --framing intermediate --timeout 60 --out auth_key.json
```


