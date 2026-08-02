from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from telecraft.tl.parser import parse_tl
from tools.gen_tl import _merge


def test_schema_files_present() -> None:
    root = Path(__file__).resolve().parents[1]
    sources = root / "src" / "telecraft" / "schema" / "sources"
    if not (sources / "api.tl").exists() or not (sources / "mtproto.tl").exists():
        pytest.skip("Schema not fetched yet. Run: python tools/fetch_schema.py")


def test_layer_pinned() -> None:
    from telecraft.schema import LAYER

    if LAYER <= 0:
        pytest.skip("Layer not pinned yet. Run: python tools/fetch_schema.py")


def test_combined_schema_has_unique_python_constructor_names() -> None:
    root = Path(__file__).resolve().parents[3]
    sources = root / "src" / "telecraft" / "schema" / "sources"
    mtproto = parse_tl((sources / "mtproto.tl").read_text(encoding="utf-8"))
    api = parse_tl((sources / "api.tl").read_text(encoding="utf-8"))

    merged = _merge(mtproto, api)
    duplicates = {
        name
        for name, count in Counter(item.name for item in merged.constructors).items()
        if count > 1
    }

    assert duplicates == set()
    vector = next(item for item in merged.constructors if item.name == "vector")
    assert vector.constructor_id == 0x1CB5C415
