# Architecture (high-level)

The project is split into layers:

- `telecraft.tl`: TL schema parsing + code generation (raw types/functions + codecs).
- `telecraft.mtproto`: transport, crypto/auth, rpc sender, sessions, updates.
- `telecraft.client.mtproto`: stable low-level MTProto-first client core.
- `telecraft.client`: developer-facing V2 structured API (`Client` + namespaces).
- `telecraft.bot`: MTProto update routing helpers (`Router` / `Dispatcher`).

Generated TL code must live under `telecraft.tl.generated/` and never be edited manually.
The public generated modules contain only the current outbound schema. Reviewed historical
constructors are generated into private inbound-only modules and normalized to current public
objects; see `docs/21_legacy_constructor_recovery.md`.

Repository-level code is organized by audience:

- `src/telecraft/`: library/product code.
- `examples/`: supported learning examples that remain in this repo.
- `apps/`: internal operator scripts and demos.
- `tools/manual/`: optional local diagnostics.
