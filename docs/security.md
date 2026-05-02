# Security notes (early)

## Sensitive material

- Session storage will contain `auth_key` (highly sensitive). Treat it as a password.
- Manual diagnostic output must not include raw `auth_key` material unless explicitly requested for
  local debugging. Never paste auth-key output into issues, chats, or release notes.

## Planned mitigations

- Optional encryption-at-rest for session storage.
- Clear documentation on threat model and safe deployment practices.

## MTProto auth handshake gotcha: RSA key selection

During auth key exchange (`req_pq_multi` → `req_DH_params`), servers return multiple RSA key
fingerprints. In practice, **a fingerprint may match but still be unusable**, resulting in a
quick-ack and then **no** `ServerDhParamsOk/Fail` response (timeout).

Telecraft mitigates this by preferring the current primary keys (see `telecraft.mtproto.auth.server_keys`)
and keeping legacy keys as fallback. If auth starts timing out again, check RSA key selection order first.

