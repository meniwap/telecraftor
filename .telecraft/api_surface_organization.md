# Telecraft API Surface Organization Plan

Internal planning file for agents. Not public docs.

Goal: keep the client API layer maintainable as Telecraft grows, without changing the public
`Client` surface, import paths, behavior, or MTProto runtime.

## Current Snapshot

- `src/telecraft/client/apis/messages.py`: 1632 lines
- `src/telecraft/client/apis/calls.py`: 685 lines
- `src/telecraft/client/apis/account.py`: 662 lines
- `src/telecraft/client/apis/stories.py`: 642 lines
- `src/telecraft/client/apis/channels.py`: 593 lines
- `src/telecraft/client/client.py`: 147 lines; no split needed
- `src/telecraft/client/apis/__init__.py`: 272 lines; keep as public export facade

The structure is already good at the namespace level. The next problem is file size inside a few
API modules, not public API shape.

## Non-Breaking Refactor Rules

- Do not change public `client.<namespace>` attributes.
- Do not change public class names currently exported from `telecraft.client.apis`.
- Do not move or edit `src/telecraft/mtproto/**`.
- Do not move or edit `src/telecraft/client/mtproto.py`.
- Keep the original module files as compatibility facades:
  - `apis/messages.py`
  - `apis/account.py`
  - `apis/calls.py`
  - `apis/stories.py`
  - `apis/channels.py`
- Move implementation into private sibling modules only.
- Each facade must re-export the same classes and keep the same `__all__` behavior where present.
- One refactor commit per namespace. Run full non-live gates after each namespace.

## Target Split

### Phase 1 - messages

Priority: highest. This file is the main maintainability risk.

Create private modules:

- `apis/_messages_base.py`: shared helpers/imports plus `MessagesAPI` root facade wiring.
- `apis/_messages_media.py`: web previews, effects, gifs, sent media, inline/prepared.
- `apis/_messages_status.py`: scheduled, receipts, saved tags, read/unread mentions/reactions.
- `apis/_messages_governance.py`: discussion, history import, chat theme, suggested posts, fact checks, sponsored, attach menu.
- `apis/_messages_core_methods.py`: high-level send/forward/delete/edit/pin/react/search/history iterators.

Keep `apis/messages.py` as a thin import/export facade.

Acceptance:

- `from telecraft.client.apis.messages import MessagesAPI` still works.
- `client.messages.*` and nested APIs are unchanged.
- Contract/unit/meta/live collect-only gates pass.

### Phase 2 - account

Create private modules:

- `apis/_account_sessions.py`: sessions, web sessions, content, ttl, terms.
- `apis/_account_appearance.py`: themes, wallpapers, profile tab, gift themes.
- `apis/_account_identity.py`: music, paid messages, passkeys, identity, personal channel.

Keep `apis/account.py` as a thin import/export facade.

Acceptance:

- `client.account.sessions`, `client.account.themes`, `client.account.identity`, and all existing nested attributes are unchanged.

### Phase 3 - calls

Create private modules:

- `apis/_calls_refs.py`: call-specific helper conversion imports and shared wrapper helpers.
- `apis/_calls_group.py`: group calls and group chain.
- `apis/_calls_stream.py`: RTMP/presentation stream controls.
- `apis/_calls_conference.py`: conference operations.

Keep `apis/calls.py` as a thin import/export facade.

Acceptance:

- `client.calls.group`, `client.calls.stream`, and `client.calls.conference` are unchanged.
- Write/destructive calls stay behind existing live flags.

### Phase 4 - stories

Create private modules:

- `apis/_stories_read.py`: capabilities, feed, links, views, reactions, peers.
- `apis/_stories_albums.py`: albums API.
- `apis/_stories_write.py`: send/edit/delete/pin/react/report/toggle APIs.

Keep `apis/stories.py` as a thin import/export facade.

Acceptance:

- `client.stories.feed`, `client.stories.albums`, `client.stories.views`, and write methods are unchanged.
- Stories write live policy remains opt-in.

### Phase 5 - channels

Create private modules:

- `apis/_channels_settings.py`: settings/admin-facing toggles.
- `apis/_channels_discovery.py`: search posts, links, admin log.
- `apis/_channels_core_methods.py`: read/delete history, participant history, message author.

Keep `apis/channels.py` as a thin import/export facade.

Acceptance:

- `client.channels.settings`, `client.channels.admin_log`, `client.channels.links`, and `client.channels.search_posts` are unchanged.
- Admin/write-sensitive live policy remains opt-in.

## Required Verification Per Phase

Run after each namespace split:

```bash
./.venv/bin/python -m ruff check src tests tools apps
./.venv/bin/python -m mypy src
PYTHONPATH=src ./.venv/bin/python -m pytest tests/meta -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/unit/client/v2 -q
PYTHONPATH=src ./.venv/bin/python -m pytest -m "not live" -q
PYTHONPATH=src ./.venv/bin/python -m pytest tests/live --collect-only -q
```

Run prod-safe live only after all non-live gates pass and only if the change touches code paths
included in `live_prod_safe`.

## Recommended Execution Order

1. Split `messages.py`.
2. Split `account.py`.
3. Split `calls.py`.
4. Split `stories.py`.
5. Split `channels.py`.
6. Update this file with final module sizes and verification evidence.

## Blockers / Risks

- Public import compatibility must be preserved exactly.
- Circular imports are likely if shared helpers are not moved first.
- Type-check drift is possible if implementation classes are renamed; prefer moving classes unchanged.
- Do not combine this refactor with API additions.
