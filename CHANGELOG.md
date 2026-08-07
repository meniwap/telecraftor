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

## [0.2.2] - 2026-08-07

Production hardening release.

### Added

- Added CI gates for repository-history hygiene, the minimum supported runtime dependency and
  build backend, dependency vulnerability auditing, Ruff formatting, and a 70% branch-coverage
  floor.
- Added dependency-free credential scanning for the worktree, index, and every reachable Git blob,
  with redacted metadata-only findings and detection of Telecraft session auth keys even under
  arbitrary filenames.
- Added immutable Telegram Desktop schema provenance, deterministic regeneration checks, and
  generated TL bindings for Layer 228.
- Added cumulative stable-API signature snapshots, including the primary client constructors, so
  removals, positional reordering, required additions, and silent default/type changes fail CI.
- Added dynamic DC discovery and bounded handling for PHONE/NETWORK/USER/FILE migration responses.
- Added configurable FloodWait retry policy, total RPC deadlines, strict update-checkpoint
  persistence, cross-process session-file locking, and durable per-channel PTS checkpoints.

### Changed

- Raised the minimum supported `cryptography` version to `50.0.0` and the minimum supported
  Hatchling build backend to `1.26.3`.
- Corrected public version status: unpublished `0.2.1` changes roll into the stable `0.2.2`
  release.
- Clarified the package boundary: wheels/source archives contain the library, not runnable bots,
  apps, examples, local operator configuration, or captures. The raw protocol method surface and
  reusable `telecraft.bot` primitives remain experimental beyond their explicitly pinned stable
  entry points.
- New facade methods now enter the support matrix as experimental until an explicit stability and
  test-tier review promotes them.

### Fixed

- Decoded binary `help.getConfig` DC addresses before caching and persistence, and repaired the
  narrowly identifiable legacy `b'<IPv4>'` session form so a successful connection cannot poison
  the next process restart.
- Prevented a saturated updates queue from blocking the shared RPC receive loop; overflow now
  schedules authoritative difference recovery instead of silently losing protocol continuity.
- Prevented lifecycle-serialized `start_updates()` and `log_out()` calls from deadlocking when
  Telegram requests a DC migration, and included time spent behind a concurrent migration in the
  caller's total RPC deadline.
- Made update-checkpoint corruption and persistence failures observable by default, with in-memory
  protocol state rolled back when a checkpoint write fails.
- Fixed stable facade parameters that were previously ignored: member-transfer `exclude_self`,
  sent-media filters/peer/pagination, and targeted message search filters.
- Made upload iteration fail explicitly on unsupported CDN redirects or invalid responses instead
  of returning a silently truncated file.
- Rejected unsupported wallpaper search controls and translate source-language overrides instead
  of accepting no-op arguments.
- Corrected WebView peer/user resolution and flags, global-search and message-effect flags, and all
  Layer 228 constructor call sites, including poll codec compatibility.

### Security

- Redacted configured Telegram API credentials from client/live-fixture representations, live step
  failures, cleanup errors, audit events, and recursively generated raw report structures.
- Excluded `cryptography` versions affected by CVE-2026-69247 / GHSA-g6cj-pr64-35w5 from the
  supported dependency range, even though Telecraft is not known to exercise the affected PKCS#7
  decryption path.
- Removed credentials, 2FA/login codes, bot tokens, API hashes, and account phone numbers from
  supported command-line argument paths. Interactive secrets use prompts where supported;
  automation should inject environment variables through a secret manager or a protected ignored
  file. This keeps values out of `argv`; inline shell assignments can still enter shell history and
  must not contain real secrets.
- Constrained the AES-ECB primitive used internally by Telegram-required IGE to exactly one block
  and documented/query-scoped its CodeQL false-positive rationale; ECB is not exposed as an
  application encryption mode.
- Added the release incident procedure required to remove private captures and local artifacts from
  all reachable history, while preserving the original published commit/tree provenance and
  treating remote caches, forks, tags, and immutable PyPI files as separate cleanup surfaces.

## [0.2.1] - 2026-08-03 (unpublished development milestone)

Production hardening and public-package follow-up release.

### Added

- Added the installed `telecraft` operator CLI, while keeping `apps/run.py` as a compatibility
  wrapper, plus a strict public resolver for the current concrete session file.
- Added auth-bound entity and updates sidecars with an explicit one-time trust option for migrating
  legacy unbound updates checkpoints without silently choosing between continuity and account
  isolation.
- Added complete recursive contract discovery for all 576 reachable high-level API call paths.

### Changed

- Raised the `cryptography` dependency floor to `48.0.1` and report the real package version in
  Telegram's `initConnection` metadata.
- Clarified that generated Telegram result objects are not all normalized into statically typed
  DTO return values.

### Fixed

- Made logout atomically tear down the connection, remove session sidecars and matching current
  pointers, and reset account identity before a waiting reconnect can proceed.
- Prevented concurrent cross-DC media clients from leaking or duplicating authorization imports.
- Preserved ordinary co-delivered updates when `updatePtsChanged` refreshes global state, recovered
  after new sessions, decode failures and idle gaps, and bounded difference pagination with
  transactional rollback.
- Implemented `dh_gen_retry` with a fresh exponent and the previous key's auxiliary hash, rejected
  oversized factorization input, and removed duplicate generated `Vector` definitions.
- Made `self`/`me` consistently use Telegram's self constructors without requiring an access hash.
- Removed unsafe blind RPC resends after ambiguous timeouts; explicit server rejection recovery
  remains bounded and validated.
- Reserved bare `self` and `me` peer aliases for the current account across message, media,
  history, and v2 peer-resolution APIs instead of resolving them as public usernames.
- Made concurrent GroupBot SQLite schema initialization retry transient `BUSY`/`LOCKED` failures
  without masking unrelated database errors.
- Updated public documentation to identify `0.2.x` as the current stable release line.

### Security

- Bounded inbound and outbound MTProto transport frames to 16 MiB.
- Accepted time/salt recovery notifications outside the normal receive window only when their
  message ID and sequence number match the active pending request, including nested containers.
- Ensured generated client message IDs have a non-zero fractional component after clock sync.
- Created GroupBot SQLite databases, WAL/SHM sidecars, and current-session pointers with private
  permissions and atomic durable replacement.
- Hid interactively entered bot tokens instead of echoing them to the terminal.
- Documented that GroupBot plugins execute with the bot process's full privileges and must be
  owner-controlled; syntax preflight is not a sandbox.
- Rejected additional control, bidirectional-spoofing, and Windows device-name variants in
  untrusted download filenames.
- Added a best-effort parent-directory durability barrier after private atomic file replacements.

## [0.2.0] - 2026-07-17

First stable production release for public MTProto user and bot sessions.

### Added

- Reworked the public examples into a documented progression covering echo, identity, messaging,
  commands, media, conversations, scheduling, and the full plugin-based group bot.
- Added typed-package metadata (`py.typed`), CPython 3.14 coverage, clean-wheel installation checks,
  strict distribution metadata validation, and artifact hygiene gates.
- Added pinned-SHA CI workflows for CodeQL, dependency review, Dependabot, package validation, and
  trusted PyPI publishing with OIDC attestations.
- Added a security policy, private-reporting route, contribution guide, Code of Conduct, issue
  forms, CODEOWNERS, support policy, and production release/incident runbook.
- Added sanitized live-evidence manifests bound to the exact commit exercised before release.
- Added `/unschedule` with persistent suppression for config-backed group-bot announcements.
- Added bounded, supervised message-handler execution with per-sender ordering, configurable
  group-bot concurrency, and conversation answers that bypass a saturated handler backlog.
- Added `same_sender=True` conversation matching for group forms while preserving the peer-wide
  public default.

### Changed

- Limited Tier A support claims to the stable methods that the prod-safe live suites actually
  exercise; all other stable methods retain Tier B compatibility support.
- Builds the exact tagged wheel and source archive once, validates them, and publishes the retained
  GitHub Actions artifact directly to production PyPI.
- Replaced captured Telegram binary fixtures with deterministic synthetic regression payloads.
- Group-bot peer scope now fails closed unless `allowed_peers` is non-empty or
  `allow_all_peers=true` is explicitly configured. Existing empty-scope deployments must migrate
  before startup.
- The group-bot validates plugin paths and syntax before connecting, treats plugin setup failure as
  fatal for the process, and applies allowed-peer guards to messages, callbacks, inline queries,
  and payment queries.

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
- Fixed `Router.ask()` races by registering waiters before sending prompts, routing answers before
  regular handlers, and cleaning pending handlers across dispatcher reconnects.
- Skipped dialog priming for bot authorizations that reject it with `BOT_METHOD_INVALID`.
- Accepted channel-history containers from Telegram and used the correct input-peer participant
  type for channel member lookup.
- Made group-bot scheduled jobs enforce allowed-peer scope and read-only mode at execution time,
  replace stale runtime closures on update, and use collision-resistant generated names.
- Preserved `/unschedule` suppression across config removal and re-addition, and made scheduler
  cancellation and shutdown safe when invoked from the running job itself.
- Prevented read-only warning, poll, quiz, content-filter, anti-flood, and scheduled-send paths from
  mutating Telegram or persistent moderation state.
- Made malformed read-only overrides fall back safely, resolved basic-group administrators from
  Telegram, and prevented temporary peer-resolution failures from disabling reconnect.
- Kept non-message updates from waiting behind the concurrent message throttle backlog and
  rate-limited overload warnings.

### Security

- Removed live Telegram payload captures from the source distribution and blocked their fixture
  directory from future tracked files and package artifacts.
- Added constant-time comparisons for known handshake nonces, hashes, inbound message keys, and
  session identifiers.
- Enforced MTProto 2.0 inbound ciphertext alignment, body and padding boundaries, server message-ID
  parity/time windows, and bounded replay detection across plain, container, and gzip payloads.
- Hid interactive 2FA entry with the platform password prompt while preserving the password bytes
  exactly as entered.

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
