# TL schema sources

These files are pinned inputs for code generation:

- `api.tl`: Telegram Core API schema (layered)
- `mtproto.tl`: MTProto schema

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
