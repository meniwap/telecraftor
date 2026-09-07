# Telecraft

[![PyPI version](https://img.shields.io/pypi/v/telecraft.svg)](https://pypi.org/project/telecraft/)
[![CI](https://github.com/meniwap/telecraftor/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/meniwap/telecraftor/actions/workflows/ci.yml)
[![Python versions](https://img.shields.io/pypi/pyversions/telecraft.svg)](https://pypi.org/project/telecraft/)
[![License: MIT-0](https://img.shields.io/pypi/l/telecraft.svg)](https://github.com/meniwap/telecraftor/blob/main/LICENSE)
[![Typing: typed](https://img.shields.io/badge/typing-typed-blue.svg)](https://peps.python.org/pep-0561/)

Telecraft is an async, MTProto-first Telegram client library for Python.

The distribution is library-only: wheels and source distributions include `src/telecraft` plus
package metadata, but do not ship `apps/`, `examples/`, operator configuration, or runnable bot
deployments. Reusable routing and bot-session primitives remain part of the library API.
For `0.2.3`, the stable compatibility contract covers the Client facade and primary client
constructors. The `telecraft.bot` routing/groupbot primitives are retained as experimental library
components, and the raw `MtprotoClient` method surface remains protocol-level experimental beyond
its versioned constructor contract. Runnable bots remain outside release artifacts.

It supports:

- user sessions for userbot workflows
- bot sessions through MTProto login with `auth.importBotAuthorization`
- high-level client namespaces for messages, dialogs, media, bots, admin helpers, and more
- an experimental reusable event stack for MTProto update routing with `Router` and `Dispatcher`

Current stable version: `0.2.3`.

Development version `0.2.1` was never tagged or published; its changes are included in the
`0.2.2` release.

Telecraft does **not** implement the HTTP Telegram Bot API. Bot accounts are supported
through MTProto, so you still need Telegram API credentials plus a bot token from BotFather.

## Supported Capabilities

- MTProto auth-key exchange uses the known-working raw RSA padding flow. RSA-PAD helpers are
  retained for a future dc-aware handshake update.
- Outbound API objects use the current pinned Layer 228 schema. Inbound decoding additionally
  recognizes the verified historical `message#9815cec8` (Layer 216) and
  `message#b92f76cf` (Layer 220) wire layouts and normalizes them to the current public `Message`
  type.
- With the updates engine running, an unknown or structurally unsafe inbound TL payload is never
  acknowledged or skipped. Telecraft replaces the TCP connection and MTProto session, repeats
  `invokeWithLayer(initConnection(...))`, and resumes `getDifference` from the last committed
  checkpoint with bounded backoff.

## Known Limitations

- This is an MTProto-first library, not a drop-in replacement for Telethon or Pyrogram.
- Method signatures are annotated, but many Telegram responses are generated TL objects whose
  concrete return types are currently exposed as `Any` rather than normalized DTOs.
- HTTP Bot API is intentionally not included; bot sessions use MTProto.
- Secret chats, calls, and full TDLib parity are not in scope for this release.
- Media downloads redirected through Telegram's CDN are not yet supported.
- Historical inbound compatibility is deliberately allowlisted rather than a complete snapshot
  of every constructor from Layers 216 and 220. An unlisted nested legacy layout fails closed and
  may end the update stream with `UpdatesRecoveryExhaustedError` after three fresh-connection
  attempts. Raw RPC calls that fail before the updates engine starts are not replayed automatically.

## Install

From PyPI:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install telecraft
```

From GitHub at the latest published stable tag:

```bash
python -m pip install "telecraft @ git+https://github.com/meniwap/telecraftor.git@v0.2.3"
```

The immutable `v0.2.3` tag identifies the source used to build the published release artifacts.

For local development from a clone:

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -U pip
./.venv/bin/python -m pip install -e ".[dev]"
```

## Credentials

Create an API app at Telegram. Load credentials from a protected file that is already ignored by
Git, or inject them with your secret manager:

```bash
cp apps/env.example.sh apps/env.sh
chmod 600 apps/env.sh
# Edit apps/env.sh locally, then load it without placing secret values in the command itself.
source apps/env.sh
```

For bot sessions, either populate `TELEGRAM_BOT_TOKEN` through that protected mechanism or leave it
unset and let `telecraft login-bot` prompt for it without echo. Environment variables keep secrets
out of `argv`, but may still be readable by same-user processes; never type real tokens or hashes
as inline shell assignments.

Local sessions contain Telegram auth keys. Treat `.sessions/` like passwords and never commit it.

## Login

The `telecraft` command included in `0.2.3` handles login and session operations.
Production access is intentionally double-gated:

```bash
TELECRAFT_ALLOW_PROD=1 telecraft login --runtime prod --allow-prod
```

The phone prompt happens before Telecraft opens a Telegram connection. After the code is sent,
Telecraft keeps the connection alive while you type the code or 2FA password.

Check the session:

```bash
TELECRAFT_ALLOW_PROD=1 telecraft me --runtime prod --allow-prod
```

Send a message:

```bash
TELECRAFT_ALLOW_PROD=1 telecraft send @your_username "hello from Telecraft" --runtime prod --allow-prod
```

## Minimal Use

```python
import asyncio

from telecraft.client import Client, ClientInit, resolve_current_session_path


async def main() -> None:
    client = Client(
        network="prod",
        session_path=resolve_current_session_path(),
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
TELECRAFT_ALLOW_PROD=1 telecraft login-bot --runtime prod --allow-prod
```

Bot sessions use a separate pointer at `.sessions/prod/current_bot`.

Run a bot session check:

```bash
TELECRAFT_ALLOW_PROD=1 telecraft me --runtime prod --allow-prod --session-kind bot
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
./.venv/bin/python -m pytest -m "not live" --cov=telecraft --cov-report=term-missing
./.venv/bin/python -m pytest tests/live --collect-only -q
./.venv/bin/python -m build
./.venv/bin/python tools/check_repo_hygiene.py --artifacts
```

Live tests are opt-in, production-gated, and documented in `docs/11_live_runbook.md`.

## Safety

- Start production adoption with controlled accounts and chats, especially for destructive or
  administrative flows.
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
- Credential scanning: `docs/19_credential_scanning.md`
- History cleanup provenance: `docs/20_history_cleanup_record.md`
- Legacy constructor recovery: `docs/21_legacy_constructor_recovery.md`
