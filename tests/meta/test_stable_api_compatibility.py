from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from telecraft.version import __version__
from tools.snapshot_stable_api import build_snapshot

BASELINE_DIR = Path("tests/meta")
MATRIX_PATH = Path("tests/meta/v2_method_matrix.yaml")
POSITIONAL_KINDS = {"POSITIONAL_ONLY", "POSITIONAL_OR_KEYWORD"}
VARIABLE_KINDS = {"VAR_POSITIONAL", "VAR_KEYWORD"}


def _load_baselines() -> list[dict[str, Any]]:
    paths = sorted(BASELINE_DIR.glob("stable_api_*.json"))
    assert paths, "At least one released stable-API snapshot is required"
    values: list[dict[str, Any]] = []
    for path in paths:
        value = json.loads(path.read_text(encoding="utf-8"))
        assert path.stem == "stable_api_" + value["release"].replace(".", "_")
        assert value["schema_version"] == 2
        assert re.fullmatch(r"[0-9a-f]{40}", value["source_commit"])
        assert re.fullmatch(r"[0-9a-f]{40}", value["source_tree"])
        assert isinstance(value["source_ref"], str) and value["source_ref"]
        assert isinstance(value["methods"], dict) and value["methods"]
        assert set(value["constructors"]) == {
            "telecraft.client.Client",
            "telecraft.client.ClientInit",
            "telecraft.client.mtproto.MtprotoClient",
        }
        assert value["dynamic_defaults"] == ["telecraft.client.ClientInit.app_version"]
        values.append(value)
    return values


def test_stable_api__published_0_2_0_provenance_is_preserved() -> None:
    value = next(item for item in _load_baselines() if item["release"] == "0.2.0")
    assert value["schema_version"] == 2
    assert value["source_ref"] == "v0.2.0"
    assert value["source_commit"] == "c6370b6e9fd0070f55b93ae381596211cc273f22"
    assert value["source_tree"] == "05b15b57b108e6d4bce9aa2fa4fbbb94beb1c4cb"


def _signature_errors(
    name: str,
    baseline: dict[str, Any],
    current: dict[str, Any],
    *,
    dynamic_defaults: set[str],
) -> list[str]:
    errors: list[str] = []
    baseline_parameters = baseline["parameters"]
    current_parameters = current["parameters"]
    current_by_name = {item["name"]: item for item in current_parameters}

    baseline_positional = [
        item["name"] for item in baseline_parameters if item["kind"] in POSITIONAL_KINDS
    ]
    current_positional = [
        item["name"] for item in current_parameters if item["kind"] in POSITIONAL_KINDS
    ]
    if current_positional[: len(baseline_positional)] != baseline_positional:
        errors.append(
            f"{name}: positional parameters changed order: "
            f"{baseline_positional!r} -> {current_positional!r}"
        )

    baseline_names = {item["name"] for item in baseline_parameters}
    for old in baseline_parameters:
        parameter = old["name"]
        new = current_by_name.get(parameter)
        if new is None:
            errors.append(f"{name}: removed parameter {parameter!r}")
            continue
        if new["kind"] != old["kind"]:
            errors.append(f"{name}.{parameter}: kind changed from {old['kind']} to {new['kind']}")
        if old["has_default"]:
            if not new["has_default"]:
                errors.append(f"{name}.{parameter}: optional parameter became required")
            elif (
                f"{name}.{parameter}" not in dynamic_defaults
                and new["default_repr"] != old["default_repr"]
            ):
                errors.append(
                    f"{name}.{parameter}: default changed from "
                    f"{old['default_repr']} to {new['default_repr']}"
                )
        if new["annotation"] != old["annotation"]:
            errors.append(
                f"{name}.{parameter}: annotation changed from "
                f"{old['annotation']!r} to {new['annotation']!r}"
            )

    for new in current_parameters:
        if new["name"] in baseline_names or new["kind"] in VARIABLE_KINDS:
            continue
        if not new["has_default"]:
            errors.append(f"{name}: new parameter {new['name']!r} is required")

    if current["return_annotation"] != baseline["return_annotation"]:
        errors.append(
            f"{name}: return annotation changed from {baseline['return_annotation']!r} "
            f"to {current['return_annotation']!r}"
        )
    return errors


def test_stable_api__every_released_snapshot_remains_compatible() -> None:
    baselines = _load_baselines()
    current = build_snapshot(
        matrix_path=MATRIX_PATH,
        release=__version__,
        source_ref="working-tree",
        source_commit="0" * 40,
        source_tree="0" * 40,
    )

    errors: list[str] = []
    for baseline in baselines:
        release = baseline["release"]
        dynamic_defaults = set(baseline["dynamic_defaults"])
        baseline_errors: list[str] = []
        for name, old_signature in baseline["constructors"].items():
            new_signature = current["constructors"].get(name)
            if new_signature is None:
                baseline_errors.append(f"{name}: released public constructor was removed")
                continue
            baseline_errors.extend(
                _signature_errors(
                    name,
                    old_signature,
                    new_signature,
                    dynamic_defaults=dynamic_defaults,
                )
            )

        current_methods = current["methods"]
        for name, old_signature in baseline["methods"].items():
            new_signature = current_methods.get(name)
            if new_signature is None:
                baseline_errors.append(f"{name}: released stable method was removed or demoted")
                continue
            baseline_errors.extend(
                _signature_errors(
                    name,
                    old_signature,
                    new_signature,
                    dynamic_defaults=dynamic_defaults,
                )
            )
        errors.extend(f"{release}: {error}" for error in baseline_errors)

    client_init = current["constructors"]["telecraft.client.ClientInit"]
    app_version = next(item for item in client_init["parameters"] if item["name"] == "app_version")
    assert app_version["default_repr"] == repr(__version__)

    assert not errors, "Stable API compatibility regressions:\n" + "\n".join(
        f"- {error}" for error in errors
    )
