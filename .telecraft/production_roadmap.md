# Telecraft Production Roadmap

Internal planning file for agents. Not public docs.  
Before starting production-readiness work, read this file, pick one item, update status/evidence when done.

## Status Legend

- `todo`: not started
- `in_progress`: actively being worked on
- `blocked`: waiting on manual action or external condition
- `done`: completed and verified

## Current Baseline

- Non-live suite: green
- Meta gates: green
- Ruff/mypy: green
- Live collect-only: green
- Sandbox: out of scope
- Core MTProto/client runtime: do not touch unless explicitly approved
- Current prod session: blocked/manual, user will refresh later

## Roadmap Items

### PROD-001 - Roadmap Governance
- priority: `P0`
- status: `done`
- goal: Keep production-readiness work coordinated across future agents.
- next_action: Maintain this file after each production-readiness task.
- evidence: Roadmap file exists at .telecraft/production_roadmap.md, is tracked in git, and defines the agent workflow.
- blocked: `false`

### PROD-002 - Prod Session Preflight
- priority: `P0`
- status: `blocked`
- goal: Ensure live prod checks start only with a valid active production session.
- next_action: After user refreshes session, verify `apps/run.py me` and prod-safe live connect.
- evidence: Pending.
- blocked: Manual session refresh required. Current session is inactive/invalid; do not treat as code bug.

### PROD-003 - CI / Quality Gate Alignment
- priority: `P0`
- status: `todo`
- goal: Ensure CI validates the same production-quality checks used locally.
- next_action: Add/verify CI coverage for ruff on `apps`, mypy, meta, non-live pytest, live collect-only, and package build.
- evidence: Pending.
- blocked: `false`

### PROD-004 - Prod-Safe Live Gate Expansion
- priority: `P0`
- status: `todo`
- goal: Make the production-safe live gate meaningful without touching paid/admin/second-account/destructive lanes.
- next_action: Expand `live_prod_safe` baseline with safe read-only checks: profile, dialogs, search, stickers, saved dialogs, tags, wallpapers/themes/help.
- evidence: Pending.
- blocked: Requires valid prod session.

### PROD-005 - Internal Version / Release Readiness
- priority: `P1`
- status: `todo`
- goal: Align project versioning with internal `0.1.x` and later public `0.2.x`.
- next_action: Prepare `0.1.0` internal milestone plan, changelog entry, and dry-run release check.
- evidence: Pending.
- blocked: `false`

### PROD-006 - API Surface Organization
- priority: `P1`
- status: `todo`
- goal: Keep API modules maintainable as the library grows.
- next_action: Plan non-breaking split for large API files: messages, account, calls, stories, channels.
- evidence: Pending.
- blocked: No public API break allowed.

### PROD-007 - Apps / Demo Cleanup
- priority: `P1`
- status: `todo`
- goal: Separate production demos from experimental/manual scripts.
- next_action: Reclassify large demo scripts into clear demos or manual labs.
- evidence: Pending.
- blocked: `false`

### PROD-008 - Second Account / Admin Hardening
- priority: `P2`
- status: `todo`
- goal: Make ban/unban/promote/kick/add/remove flows verifiable with cleanup guarantees.
- next_action: Define manual live lane requirements and rollback checks.
- evidence: Pending.
- blocked: Requires second account and explicit user approval.

### PROD-009 - Soak / Reliability Runs
- priority: `P2`
- status: `todo`
- goal: Prove long-running stability: updates, reconnects, flood waits, timeouts.
- next_action: Design manual soak suite with clear duration and artifacts.
- evidence: Pending.
- blocked: Requires valid prod session.

### PROD-010 - Public Beta Readiness
- priority: `P3`
- status: `todo`
- goal: Prepare for future public `0.2.x` beta.
- next_action: Confirm support tiers, changelog discipline, release checklist, package build, and public docs.
- evidence: Pending.
- blocked: Depends on P0/P1 completion.
