# Telecraft Apps

This directory contains production-oriented CLI tools and demos. Secrets and sessions stay local:
`apps/env.sh`, `.sessions/`, and generated reports are ignored by git.

## Setup

From the repository root:

```bash
cd /Users/meniwap/telecraftor
python3 -m venv .venv
./.venv/bin/python -m pip install -U pip
./.venv/bin/python -m pip install -e ".[dev]"
cp apps/env.example.sh apps/env.sh
source apps/env.sh
```

## Production CLI

`apps/run.py` is the main operator CLI. Production is guarded by both an env var and a flag.

```bash
TELECRAFT_ALLOW_PROD=1 ./.venv/bin/python apps/run.py login --runtime prod --allow-prod --dc 2
TELECRAFT_ALLOW_PROD=1 ./.venv/bin/python apps/run.py me --runtime prod --allow-prod --dc 2
TELECRAFT_ALLOW_PROD=1 ./.venv/bin/python apps/run.py send-self "hi" --runtime prod --allow-prod
TELECRAFT_ALLOW_PROD=1 ./.venv/bin/python apps/run.py updates --runtime prod --allow-prod --dc 2
```

Bot login stores a separate bot session:

```bash
TELECRAFT_ALLOW_PROD=1 ./.venv/bin/python apps/run.py login-bot --runtime prod --allow-prod --dc 2
TELECRAFT_ALLOW_PROD=1 ./.venv/bin/python apps/run.py me --runtime prod --allow-prod --session-kind bot --dc 2
```

## Userbot Demos

These use the MTProto user session.

```bash
TELECRAFT_ALLOW_PROD=1 ./.venv/bin/python apps/echo_bot.py --runtime prod --allow-prod
TELECRAFT_ALLOW_PROD=1 ./.venv/bin/python apps/command_bot.py --runtime prod --allow-prod
TELECRAFT_ALLOW_PROD=1 ./.venv/bin/python apps/selftest_bot.py --runtime prod --allow-prod
```

- `echo_bot.py`: echoes incoming messages where peer resolution is available.
- `command_bot.py`: command-style demo, including `/ping` and `/send`.
- `selftest_bot.py`: local self-test flow for bot framework behavior.

## MTProto Bot Demos

These use the MTProto bot session created by `apps/run.py login-bot`.

```bash
TELECRAFT_ALLOW_PROD=1 ./.venv/bin/python apps/bot_keyboard_demo.py \
  --runtime prod --allow-prod --target @meniwap
```

`bot_keyboard_demo.py` sends inline buttons and handles callback queries.

## Group Bot Demo

`group_bot.py` is a plugin-based group bot demo with SQLite-backed state.

```bash
TELECRAFT_ALLOW_PROD=1 ./.venv/bin/python apps/group_bot.py \
  --runtime prod --allow-prod --config apps/bot_config.json
```

Plugins live under `apps/bot_plugins/`. The config supports `allowed_peers`, permissions, and
`read_only_mode` for dangerous actions. See `docs/16_group_bot_guide.md` for the full guide.

## Bot API Demo

`apps/streamingbot/` is intentionally not MTProto. It uses Telegram's Bot API
`sendMessageDraft` endpoint for private-chat draft streaming.

```bash
source apps/env.sh
export TELEGRAM_STREAMING_BOT_TOKEN="123456:ABC..."
./.venv/bin/python -m apps.streamingbot.main
```

See `apps/streamingbot/README.md` for commands and behavior.

## Manual Labs

Manual labs live under `apps/manual_labs/`. They are exploratory scripts, not production demos,
and they are not part of production-readiness gates.

```bash
source apps/env.sh
TELECRAFT_ALLOW_PROD=1 ./.venv/bin/python apps/manual_labs/test_new_features.py
```

## Local State

The following files are local-only and must not be committed:

- `.sessions/prod/prod_dcX.session.json`
- `.sessions/prod/prod_dcX.bot.session.json`
- `.sessions/prod/prod_dcX.updates.json`
- `.sessions/prod/prod_dcX.entities.json`
- `.sessions/prod/current`
- `.sessions/prod/current_bot`
- `apps/env.sh`
