# Support Policy (Public API)

This document defines Telecraft's public support contract for the V2 API surface.

## Release lines

- `0.1.x`: internal line (no public support commitment by default)
- `0.2.x`: first public line (`alpha` / `beta` / `rc` / stable)

`0.1.x` can move fast and is allowed to change without public release obligations.
When a version is released publicly from the `0.2.x` line, the policy below applies.

## Stability labels

- `stable`: additive changes + documented deprecation policy
- `experimental`: best-effort, breaking changes may happen between releases

Stability is tracked per method in `tests/meta/v2_method_matrix.yaml`.

## Support tiers

Support tier is tracked in `tests/meta/v2_support_contract.json`.

- `Tier A`:
  - stable methods only
  - publicly supported
  - release-gated (must be covered by the manual `prod_safe` release evidence)
  - intended for core day-to-day userbot workflows
- `Tier B`:
  - stable methods only
  - supported with unit/meta coverage and compatibility guarantees
  - not required to be live-gated on every public release
  - suitable for environment-specific or broader API coverage that is stable but not in the release smoke set
- `experimental`:
  - no compatibility guarantee
  - opt-in live lanes/flags where relevant
  - may change faster than stable tiers

## Compatibility policy (`0.x` strict)

Telecraft remains in `0.x`, but stable APIs follow a strict compatibility model:

- no undocumented breaking changes in `stable`
- prefer additive changes
- breaking stable changes require deprecation first
- `experimental` may change without the same guarantees

## Deprecation policy (stable APIs)

Stable API deprecations are tracked in `tests/meta/v2_deprecations.json`.

Rules:
- deprecations must include `deprecated_in` and `remove_in`
- removal is not allowed before **2 minor releases** (`remove_in >= deprecated_in + 2 minors`)
- deprecations must be documented in:
  - `CHANGELOG.md` (`Deprecated` / `Removed` sections)
  - `docs/10_v2_migration.md`

## Release-gated live evidence (public releases only)

For public releases (`0.2.x` line and above), Telecraft requires a manual production live gate:

- `live_core_safe`
- `live_prod_safe` optional baseline

This gate is run manually and validated by `tools/release_check.py` using the generated live artifacts.

Internal `0.1.x` milestones do not require this gate.

## What is and is not guaranteed

Guaranteed for stable methods (Tier A/B):
- method exists and is tracked in the matrix
- required unit/meta coverage scenarios exist
- compatibility follows additive + deprecation policy

Not guaranteed (or best-effort only):
- experimental API behavior across releases
- expensive/paid/admin-heavy live paths on every release
- environment-specific capabilities that require account permissions/features

## Reporting regressions

When reporting a regression, include:
- Telecraft version
- whether the method is `stable` or `experimental`
- method name / namespace (for example `messages.send`, `dialogs.list`)
- traceback and RPC error text (if any)
- whether the issue reproduces in non-live unit tests or only in live runs

## Related docs

- `docs/13_api_capability_map.md`
- `docs/18_release_process.md`
- `docs/11_live_runbook.md`
