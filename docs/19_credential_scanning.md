# Credential Scanning

Telecraft ships a small, dependency-free scanner for release gating. It is deliberately focused on
credential shapes that have a low false-positive rate: private-key headers, GitHub and PyPI tokens,
AWS access keys and explicitly assigned secret/session keys, Telegram bot tokens, and literal
assignments to credential-bearing `TELEGRAM_*` variables. It also validates Telecraft's serialized
`auth_key_b64` field as a 256-byte MTProto authorization key, regardless of the session filename.

## Local commands

Scan the Git index and every tracked or untracked, non-ignored worktree file:

```bash
python tools/check_secrets.py
```

Scan every blob reachable from every local branch, tag, remote-tracking ref, or other Git ref:

```bash
python tools/check_secrets.py --history
```

The history command is local-only: it never fetches, contacts a remote, or modifies a ref. A CI
checkout must use `fetch-depth: 0` before invoking it; otherwise it can only inspect the shallow
history that is present.

On a match, the command exits with status 1 and emits deterministic JSON lines containing only
`ref`, `blob`, `path`, and `rule`. Matching file contents and line text are never printed.
Operational failures exit with status 2 and also suppress underlying Git or OS diagnostics so that
an unusual error cannot echo file contents. Paths and ref names are metadata but can themselves be
sensitive, so sanitize scanner output before sharing it outside the incident-response team.

## Responding to a match

Treat a credential committed to any reachable history as exposed. Revoke or rotate it first, then
remove the offending data from every affected ref and public artifact. Rewriting local Git history
does not invalidate a token, remove an already published package, or update a remote repository.
Run both scanner modes again after cleanup.

Do not add real credential-shaped strings as test fixtures or documentation examples. Build
synthetic test values from separate fragments, and use environment lookups or visibly symbolic
placeholders in examples.

This is a high-signal release gate, not a complete data-loss-prevention system. It does not attempt
to identify arbitrary passwords, encrypted secrets, application-specific token formats, sensitive
message contents, or personal data. Provider-side secret scanning and credential rotation remain
necessary layers. History mode scans objects reachable from current refs; reflog-only and otherwise
unreachable objects require separate object-database cleanup and verification during a purge.
