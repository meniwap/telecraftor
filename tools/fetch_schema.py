from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from telecraft.tl.parser import parse_tl  # noqa: E402

SOURCES_DIR = ROOT / "src" / "telecraft" / "schema" / "sources"
PINNED_LAYER_FILE = ROOT / "src" / "telecraft" / "schema" / "pinned_layer.py"
PROVENANCE_FILE = SOURCES_DIR / "provenance.json"

# Telegram Desktop v7.0.9. Keep this as a full commit SHA: branch names and
# tags are convenient for discovery, but are not immutable code-generation
# inputs.
DEFAULT_TDESKTOP_COMMIT = "a1e89e1f64f08cb058caf1c61ff43f319f98a6ec"
_FULL_GIT_SHA_RE = re.compile(r"[0-9a-f]{40}")
_MAX_SCHEMA_BYTES = 16 * 1024 * 1024
_MIN_API_CONSTRUCTORS = 1_000
_MIN_API_METHODS = 500
_MIN_MTPROTO_CONSTRUCTORS = 40
_MIN_MTPROTO_METHODS = 5


def _download_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "telecraft-schema-fetcher"})
    with urllib.request.urlopen(request, timeout=30) as resp:  # noqa: S310
        data = resp.read(_MAX_SCHEMA_BYTES + 1)
    if len(data) > _MAX_SCHEMA_BYTES:
        raise RuntimeError(f"Schema response is unexpectedly large: {len(data)} bytes")
    return data.decode("utf-8", errors="strict")


def _extract_layer(api_tl_text: str) -> int | None:
    # Telegram Desktop schema usually has: "// LAYER 195"
    m = re.search(r"(?m)^//\s*LAYER\s+(\d+)\s*$", api_tl_text)
    if not m:
        return None
    return int(m.group(1))


def _validate_tl_inputs(api_text: str, mtproto_text: str) -> int:
    layer = _extract_layer(api_text)
    if layer is None:
        raise RuntimeError("Could not determine LAYER from the pinned api.tl input.")
    try:
        api_schema = parse_tl(api_text, strict=True)
        mtproto_schema = parse_tl(mtproto_text, strict=True)
    except Exception as exc:
        raise RuntimeError("Downloaded TL schema is not parseable; no files were updated.") from exc
    counts = (
        len(api_schema.constructors),
        len(api_schema.methods),
        len(mtproto_schema.constructors),
        len(mtproto_schema.methods),
    )
    minimums = (
        _MIN_API_CONSTRUCTORS,
        _MIN_API_METHODS,
        _MIN_MTPROTO_CONSTRUCTORS,
        _MIN_MTPROTO_METHODS,
    )
    if any(actual < minimum for actual, minimum in zip(counts, minimums, strict=True)):
        raise RuntimeError("Downloaded TL schema is incomplete; no files were updated.")
    return layer


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _update_pinned_layer(layer: int) -> None:
    content = PINNED_LAYER_FILE.read_text(encoding="utf-8")
    new_content, n = re.subn(
        r"(?m)^LAYER:\s*int\s*=\s*\d+\s*$",
        f"LAYER: int = {layer}",
        content,
    )
    if n != 1:
        raise RuntimeError("Could not update pinned layer (unexpected file format).")
    _write_text(PINNED_LAYER_FILE, new_content)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _write_provenance(
    *,
    source: str,
    ref: str | None,
    layer: int,
    api_url: str,
    mtproto_url: str,
    api_text: str,
    mtproto_text: str,
) -> None:
    payload = {
        "schema_version": 1,
        "source": source,
        "ref": ref,
        "layer": layer,
        "api_url": api_url,
        "mtproto_url": mtproto_url,
        "api_sha256": _sha256_text(api_text),
        "mtproto_sha256": _sha256_text(mtproto_text),
    }
    _write_text(PROVENANCE_FILE, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Fetch and pin Telegram TL schemas.")
    parser.add_argument(
        "--source",
        choices=["tdesktop"],
        default="tdesktop",
        help=(
            "Schema source. Telecraft code generation supports only immutable .tl inputs from "
            "telegramdesktop/tdesktop."
        ),
    )
    parser.add_argument(
        "--ref",
        default=DEFAULT_TDESKTOP_COMMIT,
        help=(
            "Full immutable commit SHA for telegramdesktop/tdesktop schema files "
            f"(default: {DEFAULT_TDESKTOP_COMMIT})."
        ),
    )
    parser.add_argument(
        "--allow-moving-ref",
        action="store_true",
        help=(
            "Allow a branch/tag ref for one-off investigation; never use this for committed inputs."
        ),
    )
    args = parser.parse_args(argv)

    if not args.allow_moving_ref and _FULL_GIT_SHA_RE.fullmatch(args.ref) is None:
        parser.error("--ref must be a full 40-character commit SHA (or pass --allow-moving-ref)")

    api_url = (
        f"https://raw.githubusercontent.com/telegramdesktop/tdesktop/{args.ref}"
        "/Telegram/SourceFiles/mtproto/scheme/api.tl"
    )
    mtproto_url = (
        f"https://raw.githubusercontent.com/telegramdesktop/tdesktop/{args.ref}"
        "/Telegram/SourceFiles/mtproto/scheme/mtproto.tl"
    )

    api_text = _download_text(api_url)
    mtproto_text = _download_text(mtproto_url)
    layer = _validate_tl_inputs(api_text, mtproto_text)

    _write_text(SOURCES_DIR / "api.tl", api_text)
    _write_text(SOURCES_DIR / "mtproto.tl", mtproto_text)

    _update_pinned_layer(layer)
    _write_provenance(
        source=args.source,
        ref=args.ref,
        layer=layer,
        api_url=api_url,
        mtproto_url=mtproto_url,
        api_text=api_text,
        mtproto_text=mtproto_text,
    )
    print(f"Fetched schema source={args.source} (ref={args.ref}); pinned LAYER={layer}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
