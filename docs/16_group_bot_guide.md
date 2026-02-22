# Group Bot Guide (MTProto, plugin-based)

This guide describes the production-ready group bot entrypoint:
- `apps/group_bot.py`
- plugins under `apps/bot_plugins/`
- config file `apps/bot_config.json`

It is designed for MTProto bot sessions (`auth.importBotAuthorization`) and reuses Telecraft's
`Router` / `Dispatcher` stack.

## Architecture

- Runtime shell:
  - `Client` with bot session lane (`.sessions/<runtime>/current_bot`)
  - `Router` (handlers + middlewares)
  - `PluginLoader` (path-based plugin loading/reloading)
  - `Scheduler` (periodic announcements/jobs)
  - `GroupBotStorage` (SQLite for warnings/stats/settings/modlog/schedules)
- Scope safety:
  - middleware blocks events outside configured `allowed_peers`
- Privilege safety:
  - admin checks per command (`ctx.is_admin(...)`)
- Destructive safety:
  - per-peer `read_only_mode` (dry-run) stored in DB

## Plugins shipped

- `apps/bot_plugins/core.py`
  - `/start`, `/help`, `/id`, `/settings`
  - inline callbacks (`gb:*`) and read-only toggle
- `apps/bot_plugins/moderation.py`
  - `/warn`, `/warnings`, `/unwarn`
  - `/mute`, `/unmute` (backward-compatible aliases)
  - `/restrict`, `/unrestrict` with profiles: `all`, `media`, `links`, `text`
  - `/ban`, `/unban`, `/readd`, `/kick`
  - `readd` behavior: returns a self-join path (invite link when possible, otherwise manual/public join guidance)
  - anti-flood, link/keyword guards, auto warn/auto-ban threshold
- `apps/bot_plugins/welcome.py`
  - welcome/leave messages
  - member/admin state audit signals
- `apps/bot_plugins/utilities.py`
  - `/autopin`, `/poll`, `/quiz`, `/schedule`, `/jobs`
- `apps/bot_plugins/stats.py`
  - `/top`, `/stats`, `/modlog`
  - passive message counters

## Safe vs destructive operations

- Safe (read-only or low-risk):
  - `/help`, `/id`, `/top`, `/stats`, `/modlog`, `/jobs`
  - passive event tracking and audit logging
- Potentially destructive:
  - `/ban`, `/unban`, `/readd`, `/kick`
  - `/mute`, `/unmute`, `/restrict`, `/unrestrict`
  - content enforcement that deletes messages
  - scheduled messages (`/schedule`)
- In `read_only_mode=true`, destructive flows become dry-run:
  - action intent is logged/replied, no mutation is sent to Telegram

## Config schema

Main file: `apps/bot_config.json`.

Key fields:
- `allowed_peers`: list of `@username` or `channel:ID` / `chat:ID`
- `admin_user_ids`: hardcoded admins (optional fallback)
- `read_only_mode`: global default
- `warn_threshold`: auto-ban threshold
- `flood_*`: anti-flood thresholds
- `blocked_keywords`, `block_links`
- `announcements`: periodic messages (`name`, `text`, `every_seconds`, `peer`, `enabled`)
- `plugin_paths`: plugin file list

Per-peer overrides are stored in SQLite (`group_settings`) and survive restarts.

## Run

1) Login bot session (once):

```bash
./.venv/bin/python apps/run.py login-bot --runtime sandbox
```

2) Start in sandbox:

```bash
./.venv/bin/python apps/group_bot.py --runtime sandbox --config apps/bot_config.json
```

3) Start in prod (hard-gated):

```bash
TELECRAFT_ALLOW_PROD=1 ./.venv/bin/python apps/group_bot.py \
  --runtime prod \
  --allow-prod \
  --config apps/bot_config.json
```

## Group QA checklist (`@telecraftorbotandi`)

Pre-flight:
- Bot is admin with:
  - delete messages
  - ban/restrict users
  - pin messages
- BotFather privacy mode:
  - disable if full moderation over all group messages is required

Smoke:
- `/start` -> menu
- callback tap -> immediate answer (spinner clears)
- `/help`, `/id` output correctness
- `/settings` toggles read-only
- `/warn` / `/warnings` counters
- `/mute <user> 1` and `/unmute <user>`
- `/restrict <user> media 1` and `/unrestrict <user>`
- `/restrict <user> links 1` and `/unrestrict <user>`
- `/ban <user>` / `/unban <user>` / `/readd <user>` / `/kick <user>`
  - `readd`: user rejoins manually (no force-add after kick/ban)
- anti-flood by burst posting
- link/keyword guard trigger
- `/schedule 60 test message` then verify delivery

Regression:
- restart process and verify no backlog reply storms
- verify throttling under chat spam
- verify db persistence (`warnings`, `top`, `modlog`, schedules)

## Optional live automation lane

New optional lane:
- `tests/live/bot/test_live_group_bot_suite.py`

Gate:
- requires `--run-live --live-bot`
- requires both user and bot sessions
- requires env `TELECRAFT_LIVE_BOT_TEST_PEER` (group/channel where both can operate)
