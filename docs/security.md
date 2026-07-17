# Security and Session Threat Model

Use the private process in [`SECURITY.md`](../SECURITY.md) for suspected vulnerabilities. This
document describes operational risks; it is not a claim that the library or a local host is immune
to compromise.

## Assets handled by Telecraft

- Session JSON contains a plaintext, base64-encoded MTProto `auth_key`, DC endpoint, server salt,
  and session identifier. The `auth_key` must be protected like a password.
- Entity and update-state files can contain usernames, phone mappings, peer identifiers, and
  activity metadata.
- Application configuration can contain a Telegram `api_id`, `api_hash`, bot token, and account
  phone number. Login codes and two-step verification passwords may also be present briefly in the
  calling process.
- Downloads, live-test reports, protocol captures, tracebacks, and debug logs can expose message
  content or account metadata even when no credential is present.

## Storage guarantees and limits

Telecraft does **not** encrypt session files at rest. Session, entity-cache, and update-state writes
use an atomic temporary-file replacement created with mode `0600` before the first byte is written.
That permission is best-effort outside POSIX filesystems: platform ACLs may behave differently,
parent directory permissions are not tightened, and copies can inherit different permissions.

Keep sessions outside shared directories. Do not place them in source control, container images,
build contexts, CI artifacts, crash reports, or support bundles. Check permissions after copying or
restoring a session. Backups, Time Machine snapshots, cloud-sync folders, filesystem snapshots, and
developer-tool indexes can preserve deleted or older copies; protect or exclude those locations.
Disk encryption and a dedicated, least-privileged OS account reduce risk but do not replace session
revocation after suspected exposure.

Telecraft does not intentionally send analytics or crash telemetry. It necessarily sends MTProto
traffic to Telegram, and a host application, logging configuration, dependency, or observability
agent may collect data independently.

## Operational boundaries

- A process that can read a session file or inspect Telecraft's process memory may be able to use
  the account. A compromised host is outside the protection offered by file permissions.
- Do not reuse or run the same session concurrently on multiple hosts. Telegram may invalidate a
  duplicated authorization key.
- Use separate user and bot sessions and separate development and production runtimes.
- Redact identifiers, peer data, URLs, payloads, and authorization material before sharing output.
- Use only accounts and chats you are authorized to access. Supply your own Telegram API
  credentials and follow the [Telegram API Terms of Service](https://core.telegram.org/api/terms).
  Telecraft does not authorize spam, scraping without permission, or evasion of Telegram controls.

If a session may have escaped its intended host, stop using it, revoke the affected Telegram
authorization/session from an uncompromised client, rotate related credentials where applicable,
and report any Telecraft vulnerability privately. Deleting only the local file is insufficient.

## Implementation note: RSA key selection

During auth key exchange (`req_pq_multi` → `req_DH_params`), servers return multiple RSA key
fingerprints. In practice, **a fingerprint may match but still be unusable**, resulting in a
quick-ack and then **no** `ServerDhParamsOk/Fail` response (timeout).

Telecraft mitigates this by preferring the current primary keys (see `telecraft.mtproto.auth.server_keys`)
and keeping legacy keys as fallback. If auth starts timing out again, check RSA key selection order first.

## Implementation note: RSA padding mode

The current handshake uses the classic raw RSA padding flow for `req_DH_params.encrypted_data`:

```text
sha1(data) + data + random_padding
```

This restores live compatibility with Telegram for the current `p_q_inner_data` handshake.
The RSA-PAD helper remains available in code, but should only become the active path together with
the dc-aware `p_q_inner_data_dc` handshake shape.
