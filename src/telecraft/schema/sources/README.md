# TL schema sources

These files are pinned inputs for code generation:

- `api.tl`: Telegram Core API schema (layered)
- `mtproto.tl`: MTProto schema
- `legacy_api.tl`: a minimal, reviewed set of historical constructors accepted
  on inbound payloads only; these never replace the current outbound schema

Refresh/pin them with:

```bash
python tools/fetch_schema.py --source tdesktop
```

Notes:

- `--source tdesktop` downloads the raw `.tl` inputs used by Telegram Desktop (preferred for TL-based codegen).
- JSON schema endpoints are not accepted as pinning inputs because Telecraft's generator consumes
  `.tl` files. Reference-only JSON downloads must stay outside the repository and must not update
  the pinned layer or provenance.
- The default Telegram Desktop ref is a full, immutable commit SHA. Do not commit schema fetched
  from a moving branch or tag.
- `provenance.json` records the upstream commit, URLs, layer, and SHA-256 of both inputs. CI verifies
  that it matches the committed schema exactly.
- `legacy_provenance.json` pins the official Telegram Android source files used
  to transcribe and review each inbound-only layout. Legacy additions require
  an immutable upstream commit and focused byte-level decoding tests.
