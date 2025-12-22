# Architecture (high-level)

The project is split into layers:

- `telecraft.tl`: TL schema parsing + code generation (raw types/functions + codecs).
- `telecraft.mtproto`: transport, crypto/auth, rpc sender, sessions, updates.
- `telecraft.client`: developer-facing high-level API.
- `telecraft.botapi`: separate HTTP Bot API client.

Generated TL code must live under `telecraft.tl.generated/` and never be edited manually.


