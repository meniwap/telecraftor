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

- Pending.

## [0.2.0rc1] - 2026-07-15

Production-hardening release candidate for public MTProto user and bot sessions.

### Added

- Reworked the public examples into a documented progression covering echo, identity, messaging,
  commands, media, conversations, scheduling, and the full plugin-based group bot.
- Added typed-package metadata (`py.typed`), CPython 3.14 coverage, clean-wheel installation checks,
  strict distribution metadata validation, and artifact hygiene gates.
- Added pinned-SHA CI workflows for CodeQL, dependency review, Dependabot, TestPyPI rehearsal, and
  OIDC publishing with attestations.
- Added a security policy, private-reporting route, contribution guide, Code of Conduct, issue
  forms, CODEOWNERS, support policy, and production release/incident runbook.
- Added sanitized live-evidence manifests bound to the exact commit exercised before release.

### Changed

- Limited Tier A support claims to the stable methods that the prod-safe live suites actually
  exercise; all other stable methods retain Tier B compatibility support.
- Promotes the exact wheel and sdist exercised on TestPyPI to production PyPI instead of rebuilding
  separate release artifacts.
- Replaced captured Telegram binary fixtures with deterministic synthetic regression payloads.

### Fixed

- Correctly detected outgoing MTProto messages so explicitly enabled single-account bot examples
  can be exercised safely in Saved Messages without changing the incoming-only default.
- Validated Telegram's official DH safe prime, fallback safe primes, generator congruence,
  handshake nonces, SHA1 integrity, padding, and final nonce hashes during auth-key creation.
- Propagated terminal receiver failures to pending RPCs and update consumers, made connection
  teardown/reconnect complete after partial failures, eliminated raw-update queue drops, and
  closed fast-response and blocked-send shutdown races.
- Made update recovery atomic across `seq`, `pts`, and `qts` gaps, including immediate persisted
  state catch-up, replay ordering, bounded-queue rollback, and restart recovery for channel state.
- Kept context-bound `min` access hashes and entity caches from older logins out of peer
  resolution, and isolated permanently unavailable channels without terminating global updates.
- Made middleware continuation one-shot so a teardown failure cannot execute a downstream handler
  twice, and guaranteed userbot cleanup when startup fails.
- Serialized update-consumer startup and shutdown so concurrent callers cannot create duplicate
  consumers or publish a half-initialized updates engine.
- Created session, entity-cache, and update-state temporary files with private permissions before
  their first byte is written, with atomic replacement and failure cleanup.
- Hardened media downloads against path traversal, symlink escape, partial overwrite, and
  unbounded in-memory downloads, and rejected truncated or oversized declared media payloads.
- Routed Saved Messages media and album uploads through `InputPeerSelf`, matching the working text
  message path instead of resolving `self` as a username.
- Aligned live-report cleanup counts with the sanitized release-evidence schema.

### Security

- Removed live Telegram payload captures from the source distribution and blocked their fixture
  directory from future tracked files and package artifacts.
- Added constant-time comparisons for known handshake nonces, hashes, inbound message keys, and
  session identifiers.
- Enforced MTProto 2.0 inbound ciphertext alignment, body and padding boundaries, server message-ID
  parity/time windows, and bounded replay detection across plain, container, and gzip payloads.

## [0.2.0b4] - 2026-05-04

Hotfix beta for MTProto user login compatibility.

### Fixed

- Restored the auth-key exchange `req_DH_params` payload to the classic raw RSA padding flow
  (`sha1(data) + data + random_padding`) used by the current `p_q_inner_data` handshake.
- Documented that the RSA-PAD helper is retained for a future dc-aware handshake update, but is
  no longer the active auth-key exchange path in this beta.

## [0.2.0b3] - 2026-05-03

PyPI publishing prep beta for the public release line.

### Added

- Added GitHub Actions publishing through PyPI Trusted Publishing/OIDC for pushed version tags.
- Documented the required pending trusted publisher setup for the first PyPI upload.

### Changed

- Made PyPI the normal install path in the README.
- Updated release docs and support policy to include PyPI distribution for public releases.

## [0.2.0b2] - 2026-05-03

Focused hardening beta for the public GitHub release line.

### Changed

- Updated README/security wording so 2FA is typed interactively by default and RSA-PAD is documented
  as implemented, not a limitation.

### Removed

- Removed the public keyboard demo/example, keyboard builder helper, and keyboard-focused docs.

### Security

- Implemented RSA-PAD for the MTProto auth-key exchange.
- Hardened DH auth results so `auth_key` and `g_b` are fixed 256-byte values.
- Tightened session validation to reject malformed auth keys that are not exactly 256 bytes.
- Added bounded gzip unpacking for MTProto/TL gzip payloads.

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
