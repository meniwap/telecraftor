# Testing strategy

## Unit tests (fast)

- TL codec roundtrip (encode/decode)
- Transport framing encode/decode
- Crypto primitives (test vectors)

## Integration tests (optional, later)

- Login against Telegram test servers
- Basic calls: `getMe`, `getDialogs`, `sendMessage`
- Updates gap-fill scenarios


