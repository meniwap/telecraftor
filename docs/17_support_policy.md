# Support Policy

This document defines Telecraft's public API, runtime, and release support contract.

## Release lines

- `0.1.x`: internal line with no public support commitment
- `0.2.x` prereleases: public alpha, beta, and release-candidate line, starting with `0.2.0b1`
- stable releases: versions without an `a`, `b`, or `rc` suffix

`0.1.x` can move fast and is allowed to change without public release obligations.
When a version is released publicly from the `0.2.x` line, the policy below applies.
Public releases may be distributed through GitHub Releases and PyPI. Only the newest prerelease is
supported. Once stable releases exist, the newest stable minor receives fixes and the preceding
stable minor receives critical security fixes for 90 days after its successor ships. Older lines
may still install but are not maintained.

## Release semantics

- `alpha`: incomplete and intended for development; compatibility is not promised.
- `beta`: feature-complete enough for public testing; known limitations may remain.
- `release candidate`: no planned API changes before stable unless a release blocker is found.
- `stable`: passes the stable release gate and follows the compatibility and deprecation rules
  below. "Stable" describes the release contract, not an absence of bugs.

Because Telecraft is below `1.0`, users should pin a compatible version range. The project's
stricter policy still forbids undocumented breaking changes to APIs marked `stable`.

## Python and platform support

The supported CPython versions are the intersection of versions listed in `pyproject.toml` and the
green CI matrix. A version must not be advertised unless CI tests it. The intended production
matrix is CPython 3.10 through 3.14; 3.14 becomes supported only when its CI lane is green.

Python 3.10 reaches upstream end-of-life in October 2026. Telecraft will support it through
2026-10-31. A later minor release may raise the minimum to Python 3.11; the change must be announced
in the changelog and package metadata and must not occur in a patch release.

- Linux on CPython is the Tier 1 release platform and must pass the full CI suite.
- macOS and Windows on supported CPython versions are supported for normal library use, but are
  best-effort until their installation/import smoke lanes are release gates.
- PyPy and mobile/embedded Python runtimes are not currently supported.

Platform-specific defects are accepted when reproducible. Support does not extend to Python or
operating-system versions that their upstream vendors no longer secure.

## Stability labels

- `stable`: additive changes + documented deprecation policy
- `experimental`: best-effort, breaking changes may happen between releases

Stability is tracked per method in `tests/meta/v2_method_matrix.yaml`.

## Support tiers

Support tier is tracked in `tests/meta/v2_support_contract.json`.

- `Tier A`:
  - stable methods only
  - publicly supported
  - mapped to a required manual `prod_safe` suite in
    `tests/meta/v2_live_evidence_map.json`
  - release-gated by that suite's required steps
- `Tier B`:
  - stable methods only
  - supported with unit/meta coverage and compatibility guarantees
  - not required to be live-gated on every public release
  - suitable for environment-specific or broader API coverage that is stable but not in the release smoke set
- `experimental`:
  - no compatibility guarantee
  - opt-in live lanes/flags where relevant
  - may change faster than stable tiers

The union of `stable_methods` in the live-evidence map is exactly the Tier A method set; meta tests
enforce that equality. The map is intentionally explicit: a Tier A label means the method is mapped
to a required smoke suite. It does not claim that every Tier A method issues a distinct live RPC in
every release run. Tier B methods remain stable but are not represented as release-by-release live
evidence.

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

- core prod-safe smoke
- prod-safe baseline

This gate is run manually and validated by `tools/release_check.py` using the generated live artifacts.

The required step order and the stable methods represented by each suite are defined in
`tests/meta/v2_live_evidence_map.json`. For the exact commit exercised by the run, the release
checker verifies the expected steps, pass/fail and cleanup counts, connection-health summary, and a
digest of the local evidence bundle. Each raw run also records the source commit and whether the
tree was clean; generation fails unless both suites match the current clean `HEAD` and the supplied
`tested_commit`. The checker then writes a filtered manifest under
`release/evidence/<version>/`; raw events, summaries, sessions, and account content remain local and
must not be committed.

The filtered manifest records `tested_commit`. One later evidence-only commit containing exactly
`release/evidence/<version>/release_manifest.json` is permitted. `readiness.md` is local review
output and is not committed. Any other change after `tested_commit` invalidates the live evidence
and requires a new run.

Internal `0.1.x` milestones do not require this gate.

Every public prerelease and stable release requires the packaging, exact-tag artifact, security,
PyPI provenance, and rollback checks in `docs/18_release_process.md`. TestPyPI is an optional
rehearsal, not a production publishing dependency. Stable releases additionally require their
declared compatibility and support sign-off.

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

Security defects and possible session/credential exposure must be reported privately according to
`SECURITY.md`, without real authorization material.

## Telegram service boundary

Telecraft is an independent MTProto client library. Telegram availability, server behavior,
account restrictions, rate limits, and API changes are external dependencies and cannot receive a
library uptime guarantee. Users must register and protect their own `api_id` and `api_hash`, obtain
their own bot token when relevant, and comply with the
[Telegram API Terms of Service](https://core.telegram.org/api/terms). Support does not cover spam,
unauthorized collection, credential sharing, or bypassing Telegram safety or access controls.

## Related docs

- `docs/13_api_capability_map.md`
- `docs/18_release_process.md`
- `docs/11_live_runbook.md`
