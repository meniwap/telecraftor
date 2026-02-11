# telecraft

Telegram client library (MTProto-first). Work in progress.

## V2 API (structured client)

Primary high-level API is now `Client` with topic namespaces:

```python
from telecraft.client import Client, ClientInit

client = Client(
    network="prod",
    session_path=".sessions/prod_dc4.session.json",
    init=ClientInit(api_id=12345, api_hash="..."),
)
await client.connect()
await client.messages.send("@username", "hello")
await client.chats.members.add("channel:123", "@meniwap")
await client.admin.promote("channel:123", "@meniwap")
await client.close()
```

Namespaces:
- `client.messages`
- `client.media`
- `client.chats` (`client.chats.members`, `client.chats.invites`)
- `client.admin`
- `client.contacts`
- `client.polls`
- `client.folders`
- `client.dialogs` (`client.dialogs.pinned`, `client.dialogs.unread`, `client.dialogs.filters`)
- `client.stickers` (`client.stickers.sets`, `client.stickers.search`, `client.stickers.recent`, `client.stickers.favorites`, `client.stickers.emoji`)
- `client.topics` (`client.topics.forum`)
- `client.reactions`
- `client.privacy` (`client.privacy.global_settings`)
- `client.notifications` (`client.notifications.reactions`, `client.notifications.contact_signup`)
- `client.games` (`client.games.scores`)
- `client.saved` (`client.saved.gifs`, `client.saved.dialogs`, `client.saved.history`, `client.saved.reaction_tags`, `client.saved.pinned`)
- `client.stars` (`client.stars.transactions`, `client.stars.revenue`, `client.stars.forms`)
- `client.gifts` (`client.gifts.saved`, `client.gifts.resale`, `client.gifts.unique`)
- `client.business` (`client.business.links`, `client.business.profile`, `client.business.quick_replies`)
- `client.chatlists` (`client.chatlists.invites`, `client.chatlists.updates`, `client.chatlists.suggestions`)
- `client.stories` (`client.stories.capabilities`, `client.stories.feed`)
- `client.channels` (`client.channels.settings`)
- `client.peers`
- `client.profile`
- `client.presence`
- `client.updates`

Low-level `MtprotoClient` is still available from `telecraft.client.mtproto` for direct/raw operations.

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
python -m pytest -m "not live"
python -m ruff check src tests tools
python -m mypy src
```

Run live destructive suite manually:

```bash
python -m pytest -m live -vv -s \
  --run-live \
  --live-runtime sandbox \
  --live-destructive \
  --live-second-account meniwap \
  --live-audit-peer auto \
  --live-report-dir reports/live
```

`--live-second-account` should be passed as a bare username (`meniwap`) because pytest
interprets leading `@` as a response-file prefix.

Poll/scheduled step is disabled by default. Enable it explicitly:

```bash
python -m pytest tests/live/test_aggressive_suite.py -vv -s \
  --run-live \
  --live-runtime sandbox \
  --live-destructive \
  --live-second-account meniwap \
  --live-enable-polls
```

Poll close behavior:
- default: warning-only if `close` fails
- strict: fail test on close errors with `--live-strict-polls-close`

Run optional API expansion lanes:

```bash
python -m pytest tests/live/optional -m "live_optional" -vv -s \
  --run-live \
  --live-runtime sandbox \
  --live-audit-peer auto \
  --live-report-dir reports/live
```

Run safe non-paid optional lanes only (no core / no second-account / no paid / no stories-write / no channel-admin):

```bash
python -m pytest tests/live/optional \
  -m "live_optional and not live_paid and not live_business and not live_chatlists and not live_stories_write and not live_channel_admin" \
  -vv -s \
  --run-live \
  --live-runtime sandbox \
  --live-audit-peer auto \
  --live-report-dir reports/live
```

Business lane (opt-in):

```bash
python -m pytest tests/live/optional/test_live_business_suite.py -vv -s \
  --run-live \
  --live-runtime sandbox \
  --live-business
```

`business` and `chatlists` live lanes are fail-fast: unsupported/account errors fail the test.

Chatlists lane (opt-in):

```bash
python -m pytest tests/live/optional/test_live_chatlists_suite.py -vv -s \
  --run-live \
  --live-runtime sandbox \
  --live-chatlists
```

Chatlists lane requires env:
- `TELECRAFT_LIVE_CHATLIST_SLUG` (valid invite slug, without `https://t.me/addlist/` prefix)

Stories write lane (opt-in):

```bash
python -m pytest tests/live/optional/test_live_stories_write_suite.py -vv -s \
  --run-live \
  --live-runtime sandbox \
  --live-stories-write
```

Channel admin lane (opt-in):

```bash
python -m pytest tests/live/optional/test_live_channels_admin_suite.py -vv -s \
  --run-live \
  --live-runtime sandbox \
  --live-channel-admin
```

Enable paid gifts/stars lane explicitly (never on by default):

```bash
python -m pytest tests/live/optional/test_live_gifts_paid.py -vv -s \
  --run-live \
  --live-runtime sandbox \
  --live-paid \
  --live-audit-peer auto \
  --live-report-dir reports/live
```

Production live runs are hard-blocked by default. To run against prod intentionally:

```bash
TELECRAFT_ALLOW_PROD_LIVE=1 python -m pytest tests/live/core -m live_core -vv -s \
  --run-live \
  --live-runtime prod \
  --allow-prod-live \
  --live-destructive
```

## Client: peer resolution (userbot-friendly)

`telecraft` is MTProto-first and async-only. For userbots you typically want to target peers by:
- `@username` (resolve on-demand)
- `+phone` (resolve on-demand)
- cached numeric IDs (after priming / past interactions)

High-level helpers:

```python
from telecraft.client import Peer
from telecraft.client.mtproto import MtprotoClient

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
   - session pointer: `.sessions/prod/current` (points to e.g. `.sessions/prod/prod_dc4.session.json`)
   - entities cache: same basename, e.g. `.sessions/prod/prod_dc4.entities.json`
   - move it: `mv .sessions/prod/prod_dc4.entities.json .sessions/prod/prod_dc4.entities.json.bak`
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
