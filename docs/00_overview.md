# Overview

`telecraft` is an MTProto-first Telegram client library for Python (async-first).
It supports both:
- user accounts (userbot flows)
- bot accounts logged in via MTProto (`auth.importBotAuthorization`)

Current stable public line: `0.2.x`.

## Goals

- MTProto core + generated TL schema/types.
- High-level client API (Telethon/Pyrogram style) on top of a raw layer.
- One consistent event stack (`Router`/`Dispatcher`) for user and bot sessions.
- Supported in-repo examples under `examples/`.
- Internal operator scripts under `apps/`.

## Non-goals (early versions)

- Secret chats (E2E)
- Voice/video calls
- TDLib wrapper
- HTTP Bot API client module
