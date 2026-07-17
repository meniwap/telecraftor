# Userbot Guide (MTProto user account)

## What this is

A userbot in `telecraft` is your regular Telegram user account connected through MTProto.
It is event-driven and pulls updates from Telegram using the `Dispatcher`.

## Prerequisites

1. Create and activate a virtualenv.
2. Install dependencies.
3. Set your Telegram API credentials in `apps/env.sh`.

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -U pip
./.venv/bin/python -m pip install -e ".[dev]"
cp apps/env.example.sh apps/env.sh
source apps/env.sh
```

Required env vars:
- `TELEGRAM_API_ID`
- `TELEGRAM_API_HASH`

Optional:
- `TELEGRAM_PASSWORD` (if 2FA is enabled)

## Runtime safety

Production is blocked unless both are set:
- `--allow-prod`
- `TELECRAFT_ALLOW_PROD=1`

## Login (user session)

Login writes a user session file and updates the user pointer.

```bash
TELECRAFT_ALLOW_PROD=1 ./.venv/bin/python apps/run.py login --runtime prod --allow-prod --dc 2
```

Important defaults:
- session kind is `user`
- pointer file is `.sessions/<runtime>/current`

## Quick checks

```bash
TELECRAFT_ALLOW_PROD=1 ./.venv/bin/python apps/run.py me --runtime prod --allow-prod
TELECRAFT_ALLOW_PROD=1 ./.venv/bin/python apps/run.py send-self "hello from userbot" --runtime prod --allow-prod
TELECRAFT_ALLOW_PROD=1 ./.venv/bin/python apps/run.py updates --runtime prod --allow-prod
```

## Running a userbot app

Examples:
- `apps/echo_bot.py`
- `apps/command_bot.py`

```bash
TELECRAFT_ALLOW_PROD=1 ./.venv/bin/python apps/command_bot.py --runtime prod --allow-prod
```

## Minimal pattern

```python
from telecraft.bot import Dispatcher, Router, outgoing, command
from telecraft.client import Client

router = Router()

@router.on_message(outgoing() and command("ping"))
async def on_ping(e):
    await e.reply("pong")

app = Client(...)
await app.connect()
await Dispatcher(client=app.raw, router=router, ignore_outgoing=False).run()
```

## Dispatcher execution model

- The public `Dispatcher` default permits one active message handler
  (`max_concurrent_handlers=1`). Increase it explicitly when message handlers are safe to run
  concurrently. Non-message event handlers remain independent and may interleave with messages.
- With message concurrency enabled, order is preserved for each sender within a peer; different
  senders or peers may run concurrently.
- Running and waiting `MessageEvent` handlers share a supervised bound set by
  `max_pending_handlers` (default 4096). Once full, new regular message events are skipped with a
  rate-limited warning while pending conversation answers continue to pass through.
- A pending `Router.ask()` answer bypasses the handler queue, so a handler waiting for input does
  not block update ingestion.
- `Router.ask()` is peer-wide by default for compatibility. In group forms, pass
  `same_sender=True` so another member cannot answer the initiator's prompt.

## Common pitfalls

- User accounts cannot behave exactly like Bot API bots in every Telegram client UX flow.
- Sending to channels/DMs may need entity priming (`access_hash` cache). `Dispatcher` does
  best-effort priming for user sessions; bot sessions hydrate their cache from incoming updates
  because Telegram rejects dialog priming for bot authorizations.
- If you accidentally load a non-prod session, runtime isolation blocks startup.

## Session files (user kind)

Typical files:
- `.sessions/prod/prod_dcX.session.json`
- `.sessions/prod/current`

You can override selection with:
- `--session /path/to/file`
- `--session-kind user`
