# Userbot Guide (MTProto user account)

## What this is

A userbot in `telecraft` is your regular Telegram user account connected through MTProto.
It is event-driven and pulls updates from Telegram using the `Dispatcher`.

## Prerequisites

1. Create and activate a virtualenv.
2. Install dependencies.
3. Set your Telegram API credentials in `apps/env.sh`.

```bash
cd /Users/meniwap/telecraftor
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

## Runtime lanes and safety

- `sandbox` runtime -> Telegram `test` network (default)
- `prod` runtime -> Telegram `prod` network (requires explicit override)

Production is blocked unless both are set:
- `--allow-prod`
- `TELECRAFT_ALLOW_PROD=1`

## Login (user session)

Login writes a user session file and updates the user pointer.

```bash
./.venv/bin/python apps/run.py login --runtime sandbox --dc 2
```

Important defaults:
- session kind is `user`
- pointer file is `.sessions/<runtime>/current`

## Quick checks

```bash
./.venv/bin/python apps/run.py me --runtime sandbox
./.venv/bin/python apps/run.py send-self "hello from userbot" --runtime sandbox
./.venv/bin/python apps/run.py updates --runtime sandbox
```

## Running a userbot app

Examples:
- `apps/echo_bot.py`
- `apps/command_bot.py`
- `apps/selftest_bot.py`

```bash
./.venv/bin/python apps/command_bot.py --runtime sandbox
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

## Common pitfalls

- User accounts cannot behave exactly like Bot API bots in every Telegram client UX flow.
- Inline/reply keyboard interactions that are bot-centric may not appear/behave the same for user accounts.
- Sending to channels/DMs may need entity priming (`access_hash` cache). `Dispatcher` does best-effort priming on startup.
- If you accidentally mix session files between `sandbox` and `prod`, runtime isolation blocks startup.

## Session files (user kind)

Typical files:
- `.sessions/sandbox/test_dcX.session.json`
- `.sessions/sandbox/current`
- `.sessions/prod/prod_dcX.session.json`
- `.sessions/prod/current`

You can override selection with:
- `--session /path/to/file`
- `--session-kind user`
