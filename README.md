# telecraft

Telegram client library (MTProto-first). Work in progress.

## Development

Create a virtualenv and install dev dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

Run checks:

```bash
python -m pytest
python -m ruff check src tests tools
python -m mypy src
```

## Client: peer resolution (userbot-friendly)

`telecraft` is MTProto-first and async-only. For userbots you typically want to target peers by:
- `@username` (resolve on-demand)
- `+phone` (resolve on-demand)
- cached numeric IDs (after priming / past interactions)

High-level helpers:

```python
from telecraft.client import MtprotoClient, Peer

# ...
# await client.send_message("@username", "hi")
# await client.send_message(Peer.channel(123456), "hi")
```

## Reliability: auto-priming (reply/send “just works”)

Telegram requires `access_hash` to build `InputPeerUser` / `InputPeerChannel`.
After restarts or when receiving short updates, the cache may be missing hashes.

`telecraft` now applies **best-effort auto-priming + single retry** in common paths:
- `MtprotoClient.send_message(...)` / `send_message_user(...)` / `send_message_channel(...)`
- `MessageEvent.reply(...)` / `ChatActionEvent.reply(...)`

If a send fails due to missing access_hash, the client will run a small `prime_entities()` (dialogs fetch) and retry once.

### Verify manually (cold start)

1. Stop your userbot.
2. Move aside the entities cache for your current session. Example (prod):
   - session pointer: `.sessions/prod.current` (points to e.g. `.sessions/prod_dc4.session.json`)
   - entities cache: same basename, e.g. `.sessions/prod_dc4.entities.json`
   - move it: `mv .sessions/prod_dc4.entities.json .sessions/prod_dc4.entities.json.bak`
3. Start `apps/command_bot.py` again and send `/ping` from a dialog that exists in your recent dialogs.
4. Expected: it replies `pong` in the same chat (and does not fall back to Saved Messages).
## Client: Media MVP (send_file / download_media)

Minimal high-level helpers (photo/document):

```python
# Send local file (auto-detect photo vs document)
await client.send_file("@username", "pic.jpg", caption="hi")

# Force as document
await client.send_file("@username", "archive.zip", as_photo=False)

# Download from a MessageEvent (or a TL message object)
path = await client.download_media(event, dest="downloads/")
print("saved:", path)
```

## Bot runner (stable userbots)

Use `telecraft.bot.run_userbot()` to run a Router/Dispatcher with reconnect/backoff.

Smoke-test auth key exchange (test DCs):

```bash
python tools/smoke_auth_key.py --dc 2 --framing intermediate --timeout 60 --out auth_key.json
```


