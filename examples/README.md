# Telecraft Examples

Seven small, runnable programs that walk through the library — from a first
connection check to bots with conversations and scheduling. Each file is
self-contained and documented at the top.

| # | Example | What it shows |
|---|---------|---------------|
| 01 | [`01_echo_bot.py`](01_echo_bot.py) | The classic echo bot: `Router`, `Dispatcher`, `event.reply` |
| 02 | [`02_whoami.py`](02_whoami.py) | Connect with a saved session and print the logged-in account |
| 03 | [`03_send_message.py`](03_send_message.py) | Send a text message to any peer (`@username`, `self`, `user:ID`, ...) |
| 04 | [`04_command_bot.py`](04_command_bot.py) | `/ping`-style commands + `run_userbot` auto-reconnect |
| 05 | [`05_download_media.py`](05_download_media.py) | Iterate messages and download the newest attachment |
| 06 | [`06_conversation_form.py`](06_conversation_form.py) | Multi-step dialogs with the Router's built-in `ask()` |
| 07 | [`07_scheduled_reminders.py`](07_scheduled_reminders.py) | `/remind` command backed by the built-in `Scheduler` |

An eighth, full-scale example lives in [`group_bot/`](group_bot/) — a
plugin-based group moderation bot with persistent storage.

## Prerequisites

1. **Credentials** — export your Telegram API credentials (from
   [my.telegram.org](https://my.telegram.org)):

   ```bash
   export TELEGRAM_API_ID=123456
   export TELEGRAM_API_HASH=your_api_hash
   ```

2. **A session** — the examples load `.sessions/prod/current` by default
   (override with `TELECRAFT_SESSION_PATH`). Create one with the login flow
   described in the main [README](../README.md#login).

## Running

From the repository root:

```bash
python examples/02_whoami.py          # sanity check: who am I?
python examples/01_echo_bot.py        # then message yourself from another account
```

### Testing bots with a single account

The bot examples react to **incoming** messages by default, like a real bot.
If you only have one account handy, set:

```bash
TELECRAFT_ALLOW_OUTGOING=1 python examples/01_echo_bot.py
```

and talk to the bot in your own **Saved Messages** — the dispatcher will then
react to your outgoing messages too.
