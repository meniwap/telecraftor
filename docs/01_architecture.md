# Architecture (high-level)

The project is split into layers:

- `telecraft.tl`: TL schema parsing + code generation (raw types/functions + codecs).
- `telecraft.mtproto`: transport, crypto/auth, rpc sender, sessions, updates.
- `telecraft.client.mtproto`: stable low-level MTProto-first client core.
- `telecraft.client`: developer-facing V2 structured API (`Client` + namespaces).
- `telecraft.botapi`: separate HTTP Bot API client.

Generated TL code must live under `telecraft.tl.generated/` and never be edited manually.

