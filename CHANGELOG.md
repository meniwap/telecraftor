# Changelog

All notable changes to this project will be documented in this file.

The format follows a simplified Keep a Changelog style:
- `Added`
- `Changed`
- `Deprecated`
- `Removed`
- `Fixed`
- `Security`

## [Unreleased]

### Added

- Pending.

### Changed

- Pending.

### Removed

- Removed the public keyboard demo/example, keyboard builder helper, and keyboard-focused docs.

## [0.2.0b1] - 2026-05-02

First public beta for GitHub distribution.

### Added

- Public beta README with install, login, user session, MTProto bot session, and example flows.
- Public package metadata, project URLs, beta classifiers, and MIT-0 license metadata.
- Release hygiene checks for private planning files, local sessions, runtime reports, caches, and env files.
- Safer auth-key smoke diagnostic output that redacts `auth_key_b64` unless explicitly requested.

### Changed

- License changed from MIT to MIT No Attribution (`MIT-0`).
- Version line moved from internal `0.1.x` to public beta `0.2.0b1`.
- Interactive login waits for code/2FA input without blocking the event loop and sends keepalive pings while waiting.

### Security

- `.telecraft/` planning files are local-only and blocked from tracked files and release artifacts.
- Session/auth diagnostic tooling no longer emits raw auth keys by default.

## [0.1.0] - 2026-04-30

Internal milestone only; not a public release.

### Added

- Governance and release-readiness process docs (`support policy`, `release process`)
- Support contract and deprecation registry meta files + enforcement tests
- `tools/release_check.py` for manual public-release readiness validation

### Changed

- Public release policy clarified: `0.1.x` internal line, `0.2.x` first public line
- Public releases require manual `prod_safe` live evidence (core safe + baseline)

## [0.0.1]

- Project bootstrap.
