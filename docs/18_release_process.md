# Release Process (Manual, Pre-release Aware)

This document defines the manual release process for Telecraft public releases.

## Release lines

- `0.1.x`: internal milestones (no public release requirement)
- `0.2.x`: public line
  - `0.2.0aN` = alpha
  - `0.2.0bN` = beta
  - `0.2.0rcN` = release candidate
  - `0.2.0` = stable public release

## Versioning policy (`0.x` strict)

Telecraft is still `0.x`, but public stable APIs follow an almost-SemVer policy:
- stable: additive + deprecation
- experimental: best-effort / can break faster

## Public release gates (required)

These gates apply to **public releases only** (`0.2.x` line and above):

1. `ruff` green
2. `mypy` green
3. `pytest -m "not live"` green
4. `tests/meta` gates green
5. manual `prod_safe` live gate green (`live_core_safe` + `live_prod_safe` baseline)
6. changelog entry exists for the target version
7. `pyproject.toml` version matches target version
8. `tools/release_check.py` passes and emits release readiness artifacts

Internal `0.1.x` milestones may skip these gates.

## Manual release flow (public line)

## 1. Prepare version

- update `pyproject.toml` version to target (`0.2.0a1`, `0.2.0b1`, `0.2.0rc1`, or `0.2.0`)
- add a matching `CHANGELOG.md` section

## 2. Run non-live validation

```bash
python -m ruff check src tests tools
python -m mypy src
python -m pytest tests/meta -q
python -m pytest -m "not live" -q
python -m pytest tests/live --collect-only -q
```

## 3. Run mandatory prod-safe live gate (manual)

```bash
TELECRAFT_ALLOW_PROD_LIVE=1 python -m pytest tests/live/core tests/live/optional \
  -m "live and (live_core_safe or live_prod_safe)" \
  -vv -s \
  --run-live \
  --live-runtime prod \
  --allow-prod-live \
  --live-profile prod_safe \
  --live-audit-peer auto \
  --live-report-dir reports/live
```

Record the two run IDs:
- core-safe run ID
- prod-safe baseline run ID

## 4. Validate release readiness and emit manifest

```bash
python tools/release_check.py \
  --version 0.2.0b1 \
  --release-type beta \
  --prod-safe-run-core <run_id_core> \
  --prod-safe-run-baseline <run_id_baseline> \
  --write-dir reports/releases/0.2.0b1
```

Outputs:
- `release_manifest.json`
- `readiness.md`

## 5. Tag and push (manual)

After readiness passes:
- create tag for the target version
- push branch + tag
- publish package/release notes manually (when desired)

## Release type expectations

- `alpha`: integration preview, API may still move
- `beta`: broader public testing, behavior should be mostly stable
- `rc`: release candidate, only blockers/fixes should change
- `stable`: public release with normal support policy

## Abort / rollback rules

Abort the release if any of these happens:
- non-live gate fails
- `prod_safe` live gate fails
- changelog/version mismatch
- `release_check.py` reports blockers

Recommended rollback:
- keep the branch changes if they are valid but not ready
- do not tag/push a release tag
- fix blockers and rerun the process

## Hotfixes

Use the next patch version on the public line:
- example: `0.2.1` after `0.2.0`

Hotfixes still require the same public release gates unless explicitly treated as internal-only.

## Forbidden shortcuts

- public release without `prod_safe` evidence
- stable breaking change without deprecation entry
- release tag without changelog/version sync
- treating `main` development snapshots as public releases by accident

## Related docs

- `docs/17_support_policy.md`
- `docs/11_live_runbook.md`
- `docs/10_v2_migration.md`
