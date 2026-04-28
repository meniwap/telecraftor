# Streaming Bot

Bot API demo that uses Telegram's official `sendMessageDraft` method to stream
partial text in a private chat while the final message is being generated.

## Why this app uses Bot API

`telecraft` itself is MTProto-first, but Telegram documents `sendMessageDraft`
in the Bot API. This app intentionally uses plain HTTPS Bot API calls instead of
the MTProto client stack.

## Commands

- `/start` shows the welcome text and the persistent reply keyboard.
- `/help` lists the supported commands.
- `/menu` sends an inline menu plus refreshes the reply keyboard.
- `/joke קוד` streams 10 joke lines.
- `/story ישיבת צוות` streams a 7-line absurd micro-story.
- `/battle חתול | כלב` streams an 8-line comedic battle.
- `/fortune שבוע עבודה` streams an 8-line silly forecast.
- `/stop` cancels the active stream for the current private chat.

## Interaction model

- Reply keyboard in private chats: `בדיחות`, `סיפור`, `באטל`, `תחזית`, `עזרה`, `עצור`
- Inline actions under generated replies:
  - `עוד כזה`
  - `ערבב`
  - `תפריט`
  - `בדיחות`
  - `סיפור`
  - `תחזית`
  - `עצור`

## Setup

```bash
cd /Users/meniwap/telecraftor
cp apps/env.example.sh apps/env.sh
source apps/env.sh
```

Add your token to `apps/env.sh`:

```bash
export TELEGRAM_STREAMING_BOT_TOKEN="123456:ABC..."
```

## Run

```bash
cd /Users/meniwap/telecraftor
source apps/env.sh
./.venv/bin/python -m apps.streamingbot.main
```

## Behavior

- In private chat: streams a growing draft and then sends a final formatted reply.
- In groups/channels: sends a plain fallback asking the user to DM the bot.
- `sendMessageDraft` is only used in private chats, matching Telegram's Bot API docs.
- Free-form text defaults to joke mode if no command is provided.
