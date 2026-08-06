from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

import pytest

from telecraft.schema import LAYER
from telecraft.tl.generator import generate
from telecraft.tl.parser import parse_tl
from tools.fetch_schema import DEFAULT_TDESKTOP_COMMIT, _validate_tl_inputs
from tools.gen_tl import _merge

ROOT = Path(__file__).resolve().parents[3]
SOURCES = ROOT / "src" / "telecraft" / "schema" / "sources"


def test_schema_files_present() -> None:
    assert (SOURCES / "api.tl").is_file()
    assert (SOURCES / "mtproto.tl").is_file()
    assert (SOURCES / "provenance.json").is_file()


def test_layer_pinned() -> None:
    api_text = (SOURCES / "api.tl").read_text(encoding="utf-8")
    assert f"// LAYER {LAYER}" in api_text.splitlines()[-3:]


def test_schema_provenance_matches_committed_inputs() -> None:
    provenance = json.loads((SOURCES / "provenance.json").read_text(encoding="utf-8"))
    assert provenance["source"] == "tdesktop"
    assert provenance["ref"] == DEFAULT_TDESKTOP_COMMIT
    assert provenance["schema_version"] == 1
    assert provenance["layer"] == LAYER
    for name in ("api", "mtproto"):
        data = (SOURCES / f"{name}.tl").read_bytes()
        assert provenance[f"{name}_url"] == (
            "https://raw.githubusercontent.com/telegramdesktop/tdesktop/"
            f"{DEFAULT_TDESKTOP_COMMIT}/Telegram/SourceFiles/mtproto/scheme/{name}.tl"
        )
        assert provenance[f"{name}_sha256"] == hashlib.sha256(data).hexdigest()


def test_json_schema_cannot_replace_tl_pinning_inputs() -> None:
    from tools.fetch_schema import main

    with pytest.raises(SystemExit):
        main(["--source", "core-json"])


def test_malformed_tl_is_rejected_before_pinning() -> None:
    with pytest.raises(RuntimeError, match="incomplete"):
        _validate_tl_inputs("// LAYER 228\nthis is not TL\n", "---types---\n")


def test_combined_schema_has_unique_python_constructor_names() -> None:
    mtproto = parse_tl((SOURCES / "mtproto.tl").read_text(encoding="utf-8"))
    api = parse_tl((SOURCES / "api.tl").read_text(encoding="utf-8"))

    merged = _merge(mtproto, api)
    duplicates = {
        name
        for name, count in Counter(item.name for item in merged.constructors).items()
        if count > 1
    }

    assert duplicates == set()
    vector = next(item for item in merged.constructors if item.name == "vector")
    assert vector.constructor_id == 0x1CB5C415


def test_generated_schema_is_reproducible(tmp_path: Path) -> None:
    mtproto = parse_tl((SOURCES / "mtproto.tl").read_text(encoding="utf-8"), strict=True)
    api = parse_tl((SOURCES / "api.tl").read_text(encoding="utf-8"), strict=True)
    generated = generate(_merge(mtproto, api), tmp_path)
    committed = ROOT / "src" / "telecraft" / "tl" / "generated"
    for path in (generated.types_py, generated.functions_py, generated.registry_py):
        assert path.read_bytes() == (committed / path.name).read_bytes()
