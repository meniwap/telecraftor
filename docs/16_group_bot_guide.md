# Group Bot Guide (MTProto, plugin-based)

This guide describes the production-gated group bot operator entrypoint:
- `apps/group_bot.py`
- plugins under `apps/bot_plugins/`
- placeholder config template `apps/bot_config.example.json`

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
  - middleware blocks message, callback, inline, and payment events outside configured
    `allowed_peers`
- Privilege safety:
  - admin checks per command (`ctx.is_admin(...)`)
- Destructive safety:
  - per-peer `read_only_mode` (dry-run) stored in DB

## Plugins shipped

- `apps/bot_plugins/core.py`
  - `/start`, `/help`, `/id`, `/settings`
  - text-based read-only toggle through `/settings`
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
  - `/autopin`, `/poll`, `/quiz`, `/schedule`, `/unschedule`, `/jobs`
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
  - warnings are not changed and polls/quizzes are not sent
  - passive message statistics and the read-only setting itself are still stored locally
  - `/unschedule` remains available because it removes a future Telegram-side effect

## Config schema

Start from `apps/bot_config.example.json`, copy it to `.sessions/groupbot.local.json`, and fill in
your group/channel and admin IDs. The `.sessions/` directory is ignored and blocked from release
artifacts.

Key fields:
- `allowed_peers`: list of `@username`, `user:ID`, `channel:ID`, or `chat:ID`
- `allow_all_peers`: explicit opt-in for a global bot; defaults to `false` and cannot be
  combined with `allowed_peers`. Startup fails closed when neither scope is valid.
- `admin_user_ids`: hardcoded admins (optional fallback)
- `read_only_mode`: global default
- `warn_threshold`: auto-ban threshold
- `flood_*`: anti-flood thresholds
- `blocked_keywords`, `block_links`
- `announcements`: periodic messages (`name`, `text`, `every_seconds`, `peer`, `enabled`)
  - when `allow_all_peers=true`, every announcement must set `peer`; there is no implicit
    global/default destination and an omitted peer is disabled safely
- `plugin_paths`: plugin file list
- `max_concurrent_handlers`, `max_pending_handlers`: group-bot handler concurrency and bounded
  backlog (defaults: 64 active, 4096 total pending/running). Ordering is preserved per sender;
  `max_pending_handlers` must be greater than or equal to `max_concurrent_handlers`, or startup
  fails.

Plugin files are checked for existence and Python syntax before Telegram connection. An import or
`setup()` failure is fatal for that process; fix the plugin and restart instead of retrying inside a
partially registered router. Plugins execute as ordinary Python inside the bot process, with the
same access as the bot account and host user. Only load owner-controlled, reviewed plugin files;
syntax validation is not a sandbox or a trust check.

Per-peer overrides are stored in SQLite (`group_settings`) and survive restarts.

> Upgrade note: deployments created before the fail-closed scope check must add at least one
> `allowed_peers` entry. Use `allow_all_peers=true` only when a deliberately global bot is
> required; an old empty allow-list no longer starts the bot.

Scheduled jobs are re-checked against `allowed_peers` and the target peer's read-only setting on
every run. `/unschedule` permanently suppresses a config-backed announcement across restarts;
rename that announcement in the config if it must be created again. Basic `chat:` administrators
are discovered from Telegram. Anonymous administrator commands cannot be attributed to a user and
should be sent with an identifiable admin account (or replaced by a non-anonymous admin command).

## Run

1) Login bot session (once):

```bash
TELECRAFT_ALLOW_PROD=1 ./.venv/bin/python apps/run.py login-bot --runtime prod --allow-prod
```

2) Start in prod:

```bash
TELECRAFT_ALLOW_PROD=1 ./.venv/bin/python apps/group_bot.py \
  --runtime prod --allow-prod --config .sessions/groupbot.local.json
```

3) Explicit hard-gated form:

```bash
TELECRAFT_ALLOW_PROD=1 ./.venv/bin/python apps/group_bot.py \
  --runtime prod \
  --allow-prod \
  --config .sessions/groupbot.local.json
```

## Group QA checklist

Pre-flight:
- Bot is admin with:
  - delete messages
  - ban/restrict users
  - pin messages
- BotFather privacy mode:
  - disable if full moderation over all group messages is required

Smoke:
- `/start` -> menu
- `/help`, `/id` output correctness
- `/settings` toggles read-only through typed `readonly on` / `readonly off`
- `/warn` / `/warnings` counters
- `/mute <user> 1` and `/unmute <user>`
- `/restrict <user> media 1` and `/unrestrict <user>`
- `/restrict <user> links 1` and `/unrestrict <user>`
- `/ban <user>` / `/unban <user>` / `/readd <user>` / `/kick <user>`
  - `readd`: user rejoins manually (no force-add after kick/ban)
- anti-flood by burst posting
- link/keyword guard trigger
- `/schedule 60 test message` then verify delivery
- `/unschedule <job-name>` then verify it is disabled in `/jobs` and no longer runs, including
  after a restart

Regression:
- restart process and verify no backlog reply storms
- verify throttling under chat spam
- verify db persistence (`warnings`, `top`, `modlog`, schedules)

## Testing

The group bot is an internal operator app. Use the manual checklist above plus deterministic
router/dispatcher unit tests. There is no tracked live automation lane for it in the slim repo.
