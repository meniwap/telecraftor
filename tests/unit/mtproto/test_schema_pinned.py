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
    assert (SOURCES / "legacy_api.tl").is_file()
    assert (SOURCES / "legacy_provenance.json").is_file()


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


def test_legacy_schema_provenance_matches_reviewed_inputs() -> None:
    provenance = json.loads((SOURCES / "legacy_provenance.json").read_text(encoding="utf-8"))
    legacy_data = (SOURCES / "legacy_api.tl").read_bytes()

    assert provenance["source"] == "telegram-android"
    assert provenance["schema_version"] == 1
    assert len(provenance["ref"]) == 40
    assert provenance["legacy_api_sha256"] == hashlib.sha256(legacy_data).hexdigest()
    assert provenance["constructors"] == {
        "message#9815cec8": "layer216",
        "message#b92f76cf": "layer220",
        "messageMediaDice#3f7ee58b": "layer220",
        "messageMediaPhoto#695150d7": "layer223",
        "messageMediaPoll#4bd6e798": "layer223",
        "messageReplyHeader#6917560b": "layer223",
        "poll#58747131": "layer223",
        "pollAnswer#ff16e2ca": "layer223",
        "pollAnswerVoters#3b6ddad2": "layer223",
        "pollResults#7adf2420": "layer223",
    }
    legacy_schema = parse_tl(legacy_data.decode("utf-8"), strict=True)
    local_constructors = {
        f"{constructor.name}#{constructor.constructor_id & 0xFFFFFFFF:08x}"
        for constructor in legacy_schema.constructors
        if constructor.constructor_id is not None
    }
    assert local_constructors == set(provenance["constructors"])

    legacy_poll = next(
        constructor for constructor in legacy_schema.constructors if constructor.name == "poll"
    )
    poll_params = {param.name: param.type_ref.raw for param in legacy_poll.params}
    assert poll_params["open_answers"] == "flags.6?true"
    assert poll_params["revoting_disabled"] == "flags.7?true"
    assert poll_params["shuffle_answers"] == "flags.8?true"
    assert poll_params["hide_results_until_close"] == "flags.9?true"

    source_files = provenance["source_files"]
    assert source_files["TL_legacy_message.java"]["sha256"] == (
        "8bcf9fbf58ef78fbb13f22395d1790e697605a787621f21a59b222be8adad43e"
    )
    assert source_files["TLRPC.java"]["sha256"] == (
        "c3fffe2be0c2dcabacb4e6f6ccd03789e5394d86d06464cfbd778e8bda6af5e6"
    )
    recorded_sources = {
        constructor for source in source_files.values() for constructor in source["constructors"]
    }
    assert recorded_sources == set(provenance["constructors"])
    for source in source_files.values():
        assert f"/{provenance['ref']}/" in source["url"]


def test_json_schema_cannot_replace_tl_pinning_inputs() -> None:
    from tools.fetch_schema import main

    with pytest.raises(SystemExit):
        main(["--source", "core-json"])


def test_malformed_tl_is_rejected_before_pinning() -> None:
    with pytest.raises(RuntimeError, match="incomplete"):
        _validate_tl_inputs("// LAYER 228\nthis is not TL\n", "---types---\n")


def test_current_combined_schema_has_unique_python_constructor_names() -> None:
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


def test_schema_merge_preserves_same_name_constructor_id_pairs() -> None:
    layer216 = parse_tl("message#9815cec8 id:int = Message;")
    layer220 = parse_tl("message#b92f76cf id:int = Message;")

    merged = _merge(layer216, layer220)

    assert [(item.name, item.constructor_id) for item in merged.constructors] == [
        ("message", -1743401272),
        ("message", -1188071729),
    ]


def test_generator_requires_historical_duplicates_via_legacy_schema(
    tmp_path: Path,
) -> None:
    legacy = parse_tl("message#9815cec8 id:int = Message;")
    current = parse_tl("message#7600b9d3 flags:# id:int note:flags.0?string = Message;")

    with pytest.raises(ValueError, match="legacy_schema"):
        generate(_merge(legacy, current), tmp_path / "invalid")

    generated = generate(current, tmp_path / "valid", legacy_schema=legacy)
    assert generated.legacy_types_py is not None
    assert generated.legacy_normalizers_py is not None
    legacy_types = generated.legacy_types_py.read_text(encoding="utf-8")
    registry = generated.registry_py.read_text(encoding="utf-8")
    normalizers = generated.legacy_normalizers_py.read_text(encoding="utf-8")
    assert "class _LegacyMessage9815CEC8" in legacy_types
    assert "TL_INBOUND_ONLY: ClassVar[bool] = True" in legacy_types
    assert "id: Any" in legacy_types
    assert "-1743401272: _LegacyMessage9815CEC8" in registry
    assert "-1743401272: _normalize_9815cec8" in normalizers


def test_schema_merge_rejects_conflicting_definition_for_same_pair() -> None:
    first = parse_tl("message#00000001 id:int = Message;")
    conflicting = parse_tl("message#00000001 text:string = Message;")

    with pytest.raises(ValueError, match="Conflicting TL definitions"):
        _merge(first, conflicting)


def test_generated_schema_is_reproducible(tmp_path: Path) -> None:
    mtproto = parse_tl((SOURCES / "mtproto.tl").read_text(encoding="utf-8"), strict=True)
    api = parse_tl((SOURCES / "api.tl").read_text(encoding="utf-8"), strict=True)
    legacy = parse_tl((SOURCES / "legacy_api.tl").read_text(encoding="utf-8"), strict=True)
    generated = generate(_merge(mtproto, api), tmp_path, legacy_schema=legacy)
    committed = ROOT / "src" / "telecraft" / "tl" / "generated"
    generated_paths = (
        generated.types_py,
        generated.functions_py,
        generated.registry_py,
        generated.legacy_types_py,
        generated.legacy_normalizers_py,
    )
    for path in generated_paths:
        assert path is not None
        assert path.read_bytes() == (committed / path.name).read_bytes()
