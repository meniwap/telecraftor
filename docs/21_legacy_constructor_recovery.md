# Legacy constructor recovery

Telegram can return objects encoded with constructors from an older TL layer even after a client
has initialized a newer layer. Telegram specifically documents this for updates from large
channels and instructs clients to reopen the TCP connection, initialize the session again, and
invoke `getDifference`.

## Compatibility boundary

Telecraft keeps sending and receiving schemas separate:

- outbound objects always use the current pinned Layer 228 constructors;
- inbound decoding also accepts reviewed historical layouts from
  `src/telecraft/schema/sources/legacy_api.tl`;
- each historical layout is private, is blocked from serialization, and is normalized into its
  current public generated type;
- schema generation retains definitions by `(TL name, constructor ID)`, so two historical
  constructors named `message` cannot overwrite one another.

Version 0.2.3 directly covers `message#9815cec8` (Layer 216) and `message#b92f76cf` (Layer 220),
including the allowlisted reply, photo, dice, and poll layouts recorded in
`legacy_provenance.json`. This is not a claim of full compatibility with every constructor from
either historical layer. When an unlisted nested layout appears, decoding fails closed.

## Recovery contract

When the running updates engine receives an unknown constructor or another unsafe bounded TL
payload, Telecraft:

1. leaves `pts`, `qts`, `seq`, and per-channel PTS at the last committed checkpoint;
2. does not acknowledge the undecodable envelope and does not replay pending RPC calls;
3. marks the sender terminal and closes the poisoned connection;
4. opens a new TCP connection with the existing authorization key and a new MTProto session ID;
5. negotiates Layer 228 again with `invokeWithLayer(initConnection(...))`;
6. invokes `getDifference` from the saved checkpoint;
7. retries within one process-local three-attempt budget with exponential backoff.

Output produced by recovery does not reset that budget, even when a difference is non-empty or
advances `date`. The circuit is disarmed only after an independently received live input on the
replacement connection is fully decoded, delivered and persisted, and advances `pts`, `qts`,
`seq`, or a per-channel PTS cursor. If the budget is exhausted, update consumers receive
`telecraft.client.UpdatesRecoveryExhaustedError`, which is marked non-retryable.

The failed RPC itself is never replayed: Telegram might have executed it before returning an
undecodable response. If a raw RPC encounters this failure before the updates engine is running,
the caller receives a non-retryable decode error and should close the client before making an
explicit application-level decision about retrying the operation.

An external process supervisor cannot infer library retry semantics automatically. Map the
non-retryable exception to an exit status or service policy that does not restart forever.

## Verification

Deterministic tests replay exact binary layouts at root, gzip, update, message-container, and
`messages.channelMessages` boundaries. Live release testing starts the real updates engine and
exercises a fresh-session recovery path, but Telegram offers no deterministic way to request a
specific historical constructor from the production service.

References:

- [Telegram: Calling API methods](https://core.telegram.org/api/invoking)
- [Telegram: Working with updates](https://core.telegram.org/api/updates)
- [Telegram Android legacy message decoders](https://github.com/DrKLO/Telegram/blob/62b56a07ca7e30e39f7fd00a6728d6bbd716ca1c/TMessagesProj/src/main/java/org/telegram/tgnet/tl/legacy/TL_legacy_message.java)
