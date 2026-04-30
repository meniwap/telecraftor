# Telecraft

Telecraft is an async Telegram MTProto client library. The project is MTProto-first: it is meant
to provide a stable foundation for user sessions, bot sessions over MTProto, typed client
namespaces, media helpers, update dispatching, and internal production automation.

Current status: `0.1.x` is the internal production-readiness line. Public release work is deferred.

Repository boundary:

- `src/telecraft/`: library/product code
- `examples/`: supported learning examples that stay in this repository
- `apps/`: internal operator scripts and demos
- `tools/manual/`: optional manual diagnostics

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

## Minimal Use

```python
from telecraft.client import Client, ClientInit

client = Client(
    network="prod",
    session_path=".sessions/prod/current",
    init=ClientInit(api_id=12345, api_hash="..."),
)

await client.connect()
try:
    me = await client.users.full("self")
    await client.messages.send("@your_username", "hello from Telecraft")
finally:
    await client.close()
```

Low-level MTProto access remains available through `telecraft.client.mtproto.MtprotoClient`.

## Examples

Clean runnable examples live in `examples/`:

- `examples/01_get_me.py`
- `examples/02_send_message.py`
- `examples/03_download_media.py`
- `examples/04_userbot_echo.py`
- `examples/05_mtproto_bot_keyboard.py`
- `examples/group_bot/`

Internal operator tools remain under `apps/`. They are for local development and operations, not
package identity. Use `apps/bot_config.example.json` as the placeholder-only group bot config
template.

## Testing

Internal production gate:

```bash
./.venv/bin/python tools/check_repo_hygiene.py
./.venv/bin/python -m ruff check src tests tools apps examples
./.venv/bin/python -m mypy src
./.venv/bin/python -m pytest tests/meta -q
./.venv/bin/python -m pytest -m "not live" -q
./.venv/bin/python -m pytest tests/live --collect-only -q
./.venv/bin/python -m build
./.venv/bin/python tools/check_repo_hygiene.py --artifacts
```

Live tests are opt-in and production-gated. The tracked live suite is a minimal prod-safe smoke
layer; do not run real Telegram live tests without explicit approval. See `docs/11_live_runbook.md`.

## Docs

- Overview: `docs/00_overview.md`
- Architecture: `docs/01_architecture.md`
- Testing strategy: `docs/09_testing_strategy.md`
- Userbot guide: `docs/14_userbot_guide.md`
- MTProto bot guide: `docs/15_mtproto_bot_guide.md`
- Group bot guide: `docs/16_group_bot_guide.md`
- Support policy: `docs/17_support_policy.md`
- Release process: `docs/18_release_process.md`
