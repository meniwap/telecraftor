# Overview

`telecraft` is an MTProto-first Telegram client library for Python (async-first).
It supports both:
- user accounts (userbot flows)
- bot accounts logged in via MTProto (`auth.importBotAuthorization`)

## Goals (initial)

- MTProto core + generated TL schema/types.
- Clean separation between MTProto client and Bot API module.
- High-level client API (Telethon/Pyrogram style) on top of a raw layer.
- One consistent event stack (`Router`/`Dispatcher`) for user and bot sessions.

## Non-goals (early versions)

- Secret chats (E2E)
- Voice/video calls
- TDLib wrapper


