# API Capability Map (V4.2)

Source of truth for method-level coverage/stability:
- `tests/meta/v2_method_matrix.yaml`

This is a namespace-level quick map for discoverability.

## Support Tiers (Public Contract)

Support tiers are defined in `tests/meta/v2_support_contract.json` and applied per namespace/method.

- `Tier A`: stable + publicly supported + release-gated with manual `prod_safe` evidence
- `Tier B`: stable + compatibility-guaranteed, but not live-gated on every public release
- `experimental`: best-effort, no compatibility guarantee

Public release gates apply to the public line (`0.2.x` and above). Internal `0.1.x` milestones can
ship privately without the public release gate flow.

## Stable Namespaces

- `admin`
- `chats`, `chats.members`, `chats.invites`
- `contacts`, `contacts.requirements`
- `folders`
- `media`
- `messages`, `messages.scheduled`, `messages.web`, `messages.discussion`, `messages.receipts`,
  `messages.effects`, `messages.sent_media`, `messages.gifs`, `messages.inline`,
  `messages.inline.prepared`, `messages.history_import`, `messages.chat_theme`,
  `messages.suggested_posts`, `messages.fact_checks`, `messages.saved_tags`, `messages.attach_menu`
- `peers`
- `polls`
- `presence`
- `profile`
- `dialogs`, `dialogs.pinned`, `dialogs.unread`, `dialogs.filters`
- `stickers`, `stickers.sets`, `stickers.search`, `stickers.recent`, `stickers.favorites`,
  `stickers.emoji`
- `topics`, `topics.forum`
- `reactions`, `reactions.defaults`, `reactions.chat`
- `privacy`, `privacy.global_settings`
- `notifications`, `notifications.reactions`, `notifications.contact_signup`
- `games`, `games.scores`
- `saved`, `saved.gifs`, `saved.dialogs`, `saved.history`, `saved.reaction_tags`, `saved.pinned`
- `stars`, `stars.transactions`, `stars.revenue`, `stars.forms`
- `gifts`, `gifts.saved`, `gifts.resale`, `gifts.unique`
- `business`, `business.links`, `business.profile`, `business.quick_replies`
- `chatlists`, `chatlists.invites`, `chatlists.updates`, `chatlists.suggestions`
- `stories`, `stories.capabilities`, `stories.feed`, `stories.links`, `stories.views`,
  `stories.reactions`, `stories.stealth`, `stories.peers`, `stories.albums`
- `channels`, `channels.settings`, `channels.search_posts`
- `search`
- `drafts`
- `reports`
- `stats`, `stats.channels`, `stats.graph`, `stats.public_forwards`
- `discovery`, `discovery.channels`, `discovery.bots`
- `account`, `account.sessions`, `account.web_sessions`, `account.content`, `account.ttl`,
  `account.terms`, `account.themes`, `account.wallpapers`, `account.profile_tab`,
  `account.gift_themes`, `account.music`, `account.music.saved`
- `updates`

## Experimental Namespaces

- `messages.paid_reactions`
- `messages.sponsored`
- `account.paid_messages`
- `account.passkeys`
- `discovery.sponsored`
- `calls`, `calls.group`, `calls.group.chain`, `calls.stream`, `calls.conference`
- `premium`, `premium.boosts`
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
- `--live-premium`
- `--live-sponsored`
- `--live-passkeys`

## Governance

- Changes are `Additive + Deprecation` only.
- New methods must be registered in `tests/meta/v2_method_matrix.yaml`.
- Support tier and live-gate policy are defined in `tests/meta/v2_support_contract.json`.
- Stable deprecations are tracked in `tests/meta/v2_deprecations.json` (minimum window: 2 minors).
- Required unit naming format: `test_<namespace>__<method>__<scenario>`.
- Promotion from `experimental` to `stable` requires explicit matrix updates after live validation.
