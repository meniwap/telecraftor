# Telecraft Apps

`apps/` contains internal operator scripts for logging in, smoke-checking sessions, and running
MTProto userbot/bot demos. These scripts are useful for development, but the library identity lives
in `src/telecraft/` and clean examples live in `examples/`.

Secrets, sessions, local configs, downloads, and reports are ignored by git.

## Setup

From the repository root:

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -U pip
./.venv/bin/python -m pip install -e ".[dev]"
cp apps/env.example.sh apps/env.sh
source apps/env.sh
```

## Operator CLI

`apps/run.py` is the main local CLI. Production is guarded by both
`TELECRAFT_ALLOW_PROD=1` and `--allow-prod`.

```bash
TELECRAFT_ALLOW_PROD=1 ./.venv/bin/python apps/run.py login --runtime prod --allow-prod --dc 2
TELECRAFT_ALLOW_PROD=1 ./.venv/bin/python apps/run.py me --runtime prod --allow-prod --dc 2
TELECRAFT_ALLOW_PROD=1 ./.venv/bin/python apps/run.py login-bot --runtime prod --allow-prod --dc 2
```

## MTProto Demos

```bash
TELECRAFT_ALLOW_PROD=1 ./.venv/bin/python apps/echo_bot.py --runtime prod --allow-prod
TELECRAFT_ALLOW_PROD=1 ./.venv/bin/python apps/command_bot.py --runtime prod --allow-prod
TELECRAFT_ALLOW_PROD=1 ./.venv/bin/python apps/bot_keyboard_demo.py \
  --runtime prod --allow-prod --target @your_group_or_channel
```

## Group Bot

Use `apps/bot_config.example.json` as the placeholder-only template for a local ignored config.
The plugin modules live under `apps/bot_plugins/`.

```bash
TELECRAFT_ALLOW_PROD=1 ./.venv/bin/python apps/group_bot.py \
  --runtime prod --allow-prod --config path/to/groupbot.local.json
```

See `docs/16_group_bot_guide.md` for the full guide.

## Local State

The following files are local-only and must not be committed:

- `.sessions/prod/prod_dcX.session.json`
- `.sessions/prod/prod_dcX.bot.session.json`
- `.sessions/prod/prod_dcX.updates.json`
- `.sessions/prod/prod_dcX.entities.json`
- `.sessions/prod/current`
- `.sessions/prod/current_bot`
- `apps/env.sh`
- local group-bot config files
