from __future__ import annotations

import argparse
from pathlib import Path
from typing import TypeVar

from telecraft.tl.ast import TLCombinator, TLSchema
from telecraft.tl.generator import generate
from telecraft.tl.parser import parse_tl

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "src" / "telecraft" / "schema" / "sources"
OUT_DIR = ROOT / "src" / "telecraft" / "tl" / "generated"

_TLItem = TypeVar("_TLItem", bound=TLCombinator)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _merge_items(groups: tuple[tuple[_TLItem, ...], ...]) -> tuple[_TLItem, ...]:
    by_key: dict[tuple[str, int | None], _TLItem] = {}
    name_order: dict[str, int] = {}
    for group in groups:
        for item in group:
            name_order.setdefault(item.name, len(name_order))
            key = (item.name, item.constructor_id)
            existing = by_key.get(key)
            if existing is not None and existing != item:
                raise ValueError(f"Conflicting TL definitions for {key!r}")
            by_key[key] = item

    numbered_names = {item.name for item in by_key.values() if item.constructor_id is not None}
    items = tuple(
        item
        for item in by_key.values()
        if item.constructor_id is not None or item.name not in numbered_names
    )
    # Keep the public generated module stable: a concrete constructor that
    # supersedes an earlier placeholder retains that name's original slot.
    items = tuple(sorted(items, key=lambda item: name_order[item.name]))
    ids: dict[int, str] = {}
    for item in items:
        if item.constructor_id is None:
            continue
        previous = ids.get(item.constructor_id)
        if previous is not None and previous != item.name:
            raise ValueError(
                f"Constructor id {item.constructor_id} is shared by {previous!r} and {item.name!r}"
            )
        ids[item.constructor_id] = item.name
    return items


def _merge(*schemas: TLSchema) -> TLSchema:
    """Merge schemas without discarding same-name historical wire layouts.

    A wire constructor is identified by ``(name, constructor_id)``, not by its
    TL name alone.  Unnumbered primitive placeholders (notably MTProto's
    ``vector``) are dropped only when a numbered definition of the same name is
    present.  Conflicting definitions for one pair are rejected.
    """

    if not schemas:
        raise ValueError("At least one schema is required")

    return TLSchema(
        constructors=_merge_items(tuple(schema.constructors for schema in schemas)),
        methods=_merge_items(tuple(schema.methods for schema in schemas)),
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate TL Python code from pinned schema sources."
    )
    parser.add_argument(
        "--out",
        default=str(OUT_DIR),
        help="Output directory for generated package.",
    )
    args = parser.parse_args()

    api_path = SOURCES / "api.tl"
    mtproto_path = SOURCES / "mtproto.tl"
    legacy_path = SOURCES / "legacy_api.tl"
    if not api_path.exists() or not mtproto_path.exists() or not legacy_path.exists():
        raise SystemExit("Schema not found. Run: python tools/fetch_schema.py --source tdesktop")

    api = parse_tl(_read(api_path), strict=True)
    mtp = parse_tl(_read(mtproto_path), strict=True)
    legacy = parse_tl(_read(legacy_path), strict=True)
    merged = _merge(mtp, api)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "__init__.py").write_text(
        "# Auto-generated package. DO NOT EDIT.\n",
        encoding="utf-8",
        newline="\n",
    )

    files = generate(merged, out, legacy_schema=legacy)
    print("Generated:")
    print(f"  - {files.types_py}")
    print(f"  - {files.functions_py}")
    print(f"  - {files.registry_py}")
    print(f"  - {files.legacy_types_py}")
    print(f"  - {files.legacy_normalizers_py}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
