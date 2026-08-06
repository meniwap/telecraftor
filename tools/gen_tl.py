from __future__ import annotations

import argparse
from pathlib import Path

from telecraft.tl.generator import generate
from telecraft.tl.parser import parse_tl

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "src" / "telecraft" / "schema" / "sources"
OUT_DIR = ROOT / "src" / "telecraft" / "tl" / "generated"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _merge(a, b):
    # The transport schema contains primitive placeholders (notably ``vector``)
    # that are also present as real constructors in the API schema. Prefer the
    # later definition so generated Python names and registry entries are unique.
    constructors_by_name = {item.name: item for item in a.constructors}
    constructors_by_name.update({item.name: item for item in b.constructors})
    methods_by_name = {item.name: item for item in a.methods}
    methods_by_name.update({item.name: item for item in b.methods})
    return type(a)(
        constructors=tuple(constructors_by_name.values()),
        methods=tuple(methods_by_name.values()),
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
    if not api_path.exists() or not mtproto_path.exists():
        raise SystemExit("Schema not found. Run: python tools/fetch_schema.py --source tdesktop")

    api = parse_tl(_read(api_path), strict=True)
    mtp = parse_tl(_read(mtproto_path), strict=True)
    merged = _merge(mtp, api)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "__init__.py").write_text(
        "# Auto-generated package. DO NOT EDIT.\n",
        encoding="utf-8",
        newline="\n",
    )

    files = generate(merged, out)
    print("Generated:")
    print(f"  - {files.types_py}")
    print(f"  - {files.functions_py}")
    print(f"  - {files.registry_py}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
