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
- Current prod session: active/verified manually on 2026-04-30

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
- status: `done`
- goal: Ensure live prod checks start only with a valid active production session.
- next_action: Maintain session hygiene; do not reuse the same session concurrently across projects.
- evidence: `apps/run.py me` passed for user `voldelfi`; prod-safe live smoke passed with 2 selected / 2 passed (`live_core_safe` + `live_prod_safe`). Artifacts were created under `reports/live/prod/20260430T111907Z-2463fde2` and `reports/live/prod/20260430T111911Z-dda87981`.
- blocked: `false`

### PROD-003 - CI / Quality Gate Alignment
- priority: `P0`
- status: `done`
- goal: Ensure CI validates the same production-quality checks used locally.
- next_action: Add/verify CI coverage for ruff on `apps`, mypy, meta, non-live pytest, live collect-only, and package build.
- evidence: CI now runs ruff on `src tests tools apps`, mypy, meta gates, non-live pytest, live collect-only, and package build. Local verification passed: ruff, mypy, tests/meta, not-live pytest, live collect-only, and `python -m build`.
- blocked: `false`

### PROD-004 - Prod-Safe Live Gate Expansion
- priority: `P0`
- status: `done`
- goal: Make the production-safe live gate meaningful without touching paid/admin/second-account/destructive lanes.
- next_action: Keep future prod-safe additions read-only/metadata-only and require health_probe fail=0 evidence.
- evidence: Expanded `live_prod_safe` baseline into 7 read-only steps: identity/profile, dialogs, messages discovery, stickers/reactions, saved surface, account appearance, and help/config. Local gates passed: ruff, mypy, tests/meta, not-live pytest, and live collect-only. Prod-safe smoke passed with 2 selected / 2 passed; final artifacts: `reports/live/prod/20260430T113038Z-1abf8c35` (core safe, 4 health probes pass / 0 fail) and `reports/live/prod/20260430T113043Z-188292b4` (prod-safe baseline, 7 health probes pass / 0 fail).
- blocked: `false`

### PROD-005 - Internal Version / Release Readiness
- priority: `P1`
- status: `done`
- goal: Align project versioning with internal `0.1.x` and later public `0.2.x`.
- next_action: Use `0.1.x` for internal milestones only; reserve `0.2.x` for the first public release line with mandatory prod-safe evidence.
- evidence: Bumped project version to `0.1.0`, added `CHANGELOG.md` entry marking it as an internal milestone, package build produced `telecraft-0.1.0` sdist/wheel, and `tools/release_check.py --version 0.1.0 --release-type stable --dry-run` passed. Local gates passed: ruff, mypy, tests/meta, not-live pytest, and live collect-only.
- blocked: `false`

### PROD-006 - API Surface Organization
- priority: `P1`
- status: `done`
- goal: Keep API modules maintainable as the library grows.
- next_action: Execute future splits one namespace at a time, starting with `messages.py`, without changing public imports or `Client` attributes.
- evidence: Added internal organization plan at `.telecraft/api_surface_organization.md` with current file sizes, non-breaking rules, namespace-by-namespace split targets, acceptance criteria, and verification gates. No runtime code was changed.
- blocked: `false`

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
