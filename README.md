# Telecraft

Telecraft is an async, MTProto-first Telegram client library for Python.

It supports:

- user sessions for userbot workflows
- bot sessions through MTProto login with `auth.importBotAuthorization`
- typed high-level client namespaces for messages, dialogs, media, bots, admin helpers, and more
- an event stack for MTProto update routing with `Router` and `Dispatcher`

Public beta status: `0.2.0b4`.

Telecraft does **not** implement the HTTP Telegram Bot API in this beta. Bot accounts are supported
through MTProto, so you still need Telegram API credentials plus a bot token from BotFather.

## Supported Capabilities

- MTProto auth-key exchange uses the known-working raw RSA padding flow. RSA-PAD helpers are
  retained for a future dc-aware handshake update.

## Public Beta Known Limitations

- This is an MTProto-first beta, not a stable drop-in replacement for Telethon or Pyrogram.
- HTTP Bot API is intentionally not included; bot sessions use MTProto.
- Secret chats, calls, and full TDLib parity are not in scope for this beta.

## Install

From PyPI:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install telecraft
```

From GitHub for development or pre-release fallback:

```bash
python -m pip install "telecraft @ git+https://github.com/meniwap/telecraftor.git@v0.2.0b4"
```

For local development from a clone:

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -U pip
./.venv/bin/python -m pip install -e ".[dev]"
```

## Credentials

Create an API app at Telegram and export your credentials:

```bash
export TELEGRAM_API_ID="12345"
export TELEGRAM_API_HASH="your_api_hash"
```

For bot sessions, also export:

```bash
export TELEGRAM_BOT_TOKEN="123456:ABC..."
```

Local sessions contain Telegram auth keys. Treat `.sessions/` like passwords and never commit it.

## Login

The local operator CLI is under `apps/`. Production access is intentionally double-gated:

```bash
TELECRAFT_ALLOW_PROD=1 ./.venv/bin/python apps/run.py login --runtime prod --allow-prod
```

The phone prompt happens before Telecraft opens a Telegram connection. After the code is sent,
Telecraft keeps the connection alive while you type the code or 2FA password.

Check the session:

```bash
TELECRAFT_ALLOW_PROD=1 ./.venv/bin/python apps/run.py me --runtime prod --allow-prod
```

Send a message:

```bash
TELECRAFT_ALLOW_PROD=1 ./.venv/bin/python apps/run.py send @your_username "hello from Telecraft" --runtime prod --allow-prod
```

## Minimal Use

```python
import asyncio

from telecraft.client import Client, ClientInit


async def main() -> None:
    client = Client(
        network="prod",
        session_path=".sessions/prod/current",
        init=ClientInit(
            api_id=12345,
            api_hash="your_api_hash",
        ),
    )

    await client.connect()
    try:
        me = await client.profile.me()
        print(me)
        await client.messages.send("@your_username", "hello from Telecraft")
    finally:
        await client.close()


asyncio.run(main())
```

## MTProto Bot Session

Login a bot account through MTProto:

```bash
TELECRAFT_ALLOW_PROD=1 ./.venv/bin/python apps/run.py login-bot --runtime prod --allow-prod
```

Bot sessions use a separate pointer at `.sessions/prod/current_bot`.

Run a bot session check:

```bash
TELECRAFT_ALLOW_PROD=1 ./.venv/bin/python apps/run.py me --runtime prod --allow-prod --session-kind bot
```

## Examples

Runnable examples live in `examples/` (see `examples/README.md` for setup):

- `examples/01_echo_bot.py` - the classic echo bot
- `examples/02_whoami.py` - session sanity check
- `examples/03_send_message.py` - send a message to any peer
- `examples/04_command_bot.py` - `/ping`-style commands with auto-reconnect
- `examples/05_download_media.py` - download the newest attachment from a peer
- `examples/06_conversation_form.py` - multi-step dialogs via `router.ask()`
- `examples/07_scheduled_reminders.py` - `/remind` backed by the built-in scheduler
- `examples/group_bot/` - full plugin-based group moderation bot

Internal operator scripts and demos live in `apps/`.

## Testing

Normal local gate:

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

Live tests are opt-in, production-gated, and documented in `docs/11_live_runbook.md`.

## Safety

- This is beta software. Test with accounts and chats where mistakes are acceptable.
- Telegram sessions contain high-value auth material. Do not share session files or diagnostic logs.
- Public releases are provided under MIT-0, without warranty or liability.
- Destructive/admin-heavy flows should be tested manually with controlled accounts before real use.

## Docs

- Overview: `docs/00_overview.md`
- Architecture: `docs/01_architecture.md`
- Testing strategy: `docs/09_testing_strategy.md`
- Userbot guide: `docs/14_userbot_guide.md`
- MTProto bot guide: `docs/15_mtproto_bot_guide.md`
- Group bot guide: `docs/16_group_bot_guide.md`
- Support policy: `docs/17_support_policy.md`
- Release process: `docs/18_release_process.md`
