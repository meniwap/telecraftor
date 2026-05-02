# MTProto Bot Guide (bot token, no HTTP webhook)

## What this is

`telecraft` supports bot accounts through MTProto login (`auth.importBotAuthorization`).
This is not Bot API HTTP polling/webhooks. The bot still pulls updates through MTProto.
HTTP Bot API support is out of scope for the `0.2.x` public beta.

## Why use this mode

- Single MTProto stack for both user accounts and bot accounts
- Access to MTProto namespaces and capabilities beyond basic HTTP Bot API flows
- Same `Client` + `Router` + `Dispatcher` architecture

## Prerequisites

1. Create/activate venv and install project.
2. Configure credentials.
3. Add bot token from BotFather.

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
- `TELEGRAM_BOT_TOKEN`

## Login bot session

```bash
TELECRAFT_ALLOW_PROD=1 ./.venv/bin/python apps/run.py login-bot --runtime prod --allow-prod --dc 2
```

You can also pass the token directly:

```bash
TELECRAFT_ALLOW_PROD=1 ./.venv/bin/python apps/run.py login-bot --runtime prod --allow-prod --bot-token "123456:ABC..."
```

## Session isolation for bots

Bot sessions use their own lane:
- files like `.sessions/prod/prod_dc2.bot.session.json`
- pointer file `.sessions/prod/current_bot`

Regular user sessions are kept separate (`current`), so bot login does not overwrite user login.

Use bot lane explicitly in CLI commands when needed:

```bash
TELECRAFT_ALLOW_PROD=1 ./.venv/bin/python apps/run.py me --runtime prod --allow-prod --session-kind bot
TELECRAFT_ALLOW_PROD=1 ./.venv/bin/python apps/run.py updates --runtime prod --allow-prod --session-kind bot
```

## Run the group bot (plugin-based)

Use the production-ready plugin shell:

```bash
TELECRAFT_ALLOW_PROD=1 ./.venv/bin/python apps/group_bot.py \
  --runtime prod --allow-prod --config path/to/groupbot.local.json
```

For full architecture/config/QA details see:
- `docs/16_group_bot_guide.md`

## Important Telegram behavior

- A user must start/open the bot chat before the bot can DM them.
- In `process_no_reply` backlog mode, event replies are intentionally suppressed (`allow_reply=False`).

## Related V2 APIs for bots

- `client.auth.import_bot_authorization(...)`
- `client.bots.set_commands(...)`
- `client.bots.get_commands(...)`
- `client.bots.set_menu_button(...)`
- `client.messages.set_inline_bot_results(...)`
- `client.messages.set_bot_shipping_results(...)`
- `client.messages.set_bot_precheckout_results(...)`

## Production safety

Production runtime is blocked unless both are set:
- `--allow-prod`
- `TELECRAFT_ALLOW_PROD=1`

Example:

```bash
TELECRAFT_ALLOW_PROD=1 ./.venv/bin/python apps/run.py login-bot --runtime prod --allow-prod
```
