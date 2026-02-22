# MTProto Bot Guide (bot token, no HTTP webhook)

## What this is

`telecraft` supports bot accounts through MTProto login (`auth.importBotAuthorization`).
This is not Bot API HTTP polling/webhooks. The bot still pulls updates through MTProto.

## Why use this mode

- Single MTProto stack for both user accounts and bot accounts
- Access to MTProto namespaces and capabilities beyond basic HTTP Bot API flows
- Same `Client` + `Router` + `Dispatcher` architecture

## Prerequisites

1. Create/activate venv and install project.
2. Configure credentials.
3. Add bot token from BotFather.

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
- `TELEGRAM_BOT_TOKEN`

## Login bot session

```bash
./.venv/bin/python apps/run.py login-bot --runtime sandbox --dc 2
```

You can also pass the token directly:

```bash
./.venv/bin/python apps/run.py login-bot --runtime sandbox --bot-token "123456:ABC..."
```

## Session isolation for bots

Bot sessions use their own lane:
- files like `.sessions/sandbox/test_dc2.bot.session.json`
- pointer file `.sessions/sandbox/current_bot`

Regular user sessions are kept separate (`current`), so bot login does not overwrite user login.

Use bot lane explicitly in CLI commands when needed:

```bash
./.venv/bin/python apps/run.py me --runtime sandbox --session-kind bot
./.venv/bin/python apps/run.py updates --runtime sandbox --session-kind bot
```

## Run the keyboard demo

Use the included app:

```bash
./.venv/bin/python apps/bot_keyboard_demo.py --runtime sandbox --target @meniwap
```

What it does:
- sends: `אני חתול`
- adds inline buttons: `כן` / `לא`
- handles callback queries
- answers callback with a toast
- best-effort edits the original message with the selected choice

## Run the group bot (plugin-based)

Use the production-ready plugin shell:

```bash
./.venv/bin/python apps/group_bot.py --runtime sandbox --config apps/bot_config.json
```

For full architecture/config/QA details see:
- `docs/16_group_bot_guide.md`

## Important Telegram behavior

- A user must start/open the bot chat before the bot can DM them.
- Callback queries come from inline keyboard clicks; answer them quickly to avoid client-side spinner.
- In `process_no_reply` backlog mode, event replies are intentionally suppressed (`allow_reply=False`).

## Minimal callback-query pattern

```python
from telecraft.bot import Router, callback_data_startswith

router = Router()

@router.on_callback_query(callback_data_startswith("cat_"))
async def on_cat_choice(e):
    choice = e.data_text or ""
    await e.answer(message=f"picked: {choice}")
```

## Related V2 APIs for bots

- `client.auth.import_bot_authorization(...)`
- `client.bots.set_commands(...)`
- `client.bots.get_commands(...)`
- `client.bots.set_menu_button(...)`
- `client.messages.set_bot_callback_answer(...)`
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
