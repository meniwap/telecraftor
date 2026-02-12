# API Capability Map (V4.0)

Source of truth for method-level coverage/stability is:
- `tests/meta/v2_method_matrix.yaml`

This document is a namespace-level quick map.

## Stable Namespaces

- `admin`
- `chats`, `chats.members`, `chats.invites`
- `contacts`
- `folders`
- `media`
- `messages`, `messages.scheduled`
- `peers`
- `polls`
- `presence`
- `profile`
- `dialogs`, `dialogs.pinned`, `dialogs.unread`, `dialogs.filters`
- `stickers`, `stickers.sets`, `stickers.search`, `stickers.recent`, `stickers.favorites`, `stickers.emoji`
- `topics`, `topics.forum`
- `reactions`
- `privacy`, `privacy.global_settings`
- `notifications`, `notifications.reactions`, `notifications.contact_signup`
- `games`, `games.scores`
- `saved`, `saved.gifs`, `saved.dialogs`, `saved.history`, `saved.reaction_tags`, `saved.pinned`
- `stars`, `stars.transactions`, `stars.revenue`, `stars.forms`
- `gifts`, `gifts.saved`, `gifts.resale`, `gifts.unique`
- `business`, `business.links`, `business.profile`, `business.quick_replies`
- `stories`, `stories.capabilities`, `stories.feed`
- `chatlists`, `chatlists.invites`, `chatlists.updates`, `chatlists.suggestions`
- `channels`, `channels.settings`
- `search`
- `drafts`
- `reports`
- `stats`, `stats.channels`, `stats.graph`, `stats.public_forwards`
- `discovery`, `discovery.channels`, `discovery.bots`
- `account`, `account.sessions`, `account.web_sessions`, `account.content`, `account.ttl`, `account.terms`, `account.themes`, `account.wallpapers`
- `updates`

## Experimental Namespaces

- `calls`, `calls.group`, `calls.stream`, `calls.conference`
- `takeout`, `takeout.messages`, `takeout.media`
- `webapps`
- `todos`
- `translate`

## Live Optional Lanes (opt-in flags)

- `--live-business`
- `--live-chatlists`
- `--live-calls`
- `--live-calls-write`
- `--live-takeout`
- `--live-webapps`
- `--live-admin`
- `--live-stories-write`
- `--live-channel-admin`
- `--live-paid`

## Governance

- New methods must be additive and registered in `tests/meta/v2_method_matrix.yaml`.
- Required scenario test names must follow:
  - `test_<namespace>__<method>__<scenario>`
- Promotion from `experimental` to `stable` requires explicit matrix updates after live validation.
