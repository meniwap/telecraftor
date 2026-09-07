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
        symbols = value.get("symbols", {})
        assert isinstance(symbols, dict)
        assert all(
            isinstance(name, str) and isinstance(record, dict) for name, record in symbols.items()
        )
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


def _symbol_errors(
    name: str,
    baseline: dict[str, Any],
    current: dict[str, Any],
) -> list[str]:
    errors = [
        f"{name}: {field} changed from {expected!r} to {current.get(field)!r}"
        for field, expected in baseline.items()
        if field != "constructor"
        if current.get(field) != expected
    ]
    old_constructor = baseline.get("constructor")
    if old_constructor is not None:
        new_constructor = current.get("constructor")
        if new_constructor is None:
            errors.append(f"{name}: released public constructor contract was removed")
        else:
            errors.extend(
                _signature_errors(
                    f"{name}.__init__",
                    old_constructor,
                    new_constructor,
                    dynamic_defaults=set(),
                )
            )
    return errors


def test_stable_api__schema_v2_records_public_recovery_exception() -> None:
    current = build_snapshot(
        matrix_path=MATRIX_PATH,
        release=__version__,
        source_ref="working-tree",
        source_commit="0" * 40,
        source_tree="0" * 40,
    )

    assert current["schema_version"] == 2
    recovery_error = current["symbols"]["telecraft.client.UpdatesRecoveryExhaustedError"]
    assert {
        field: recovery_error[field]
        for field in ("kind", "module", "qualname", "is_exception", "retryable")
    } == {
        "kind": "class",
        "module": "telecraft.client.mtproto",
        "qualname": "UpdatesRecoveryExhaustedError",
        "is_exception": True,
        "retryable": False,
    }
    assert [parameter["name"] for parameter in recovery_error["constructor"]["parameters"]] == [
        "constructor_id",
        "expected_type",
        "path",
        "position",
        "attempts",
        "repeat_count",
        "consecutive_failure_count",
        "last_error",
    ]


def test_stable_api__older_schema_v2_snapshots_may_omit_symbols() -> None:
    old_releases = {"0.2.0", "0.2.2"}
    baselines = [item for item in _load_baselines() if item["release"] in old_releases]

    assert {item["release"] for item in baselines} == old_releases
    assert all(item.get("symbols", {}) == {} for item in baselines)


def test_stable_api__symbol_contract_detects_regression() -> None:
    baseline = {
        "kind": "class",
        "module": "telecraft.client.mtproto",
        "qualname": "UpdatesRecoveryExhaustedError",
        "is_exception": True,
        "retryable": False,
    }

    assert (
        _symbol_errors("telecraft.client.UpdatesRecoveryExhaustedError", baseline, baseline) == []
    )
    assert _symbol_errors(
        "telecraft.client.UpdatesRecoveryExhaustedError",
        baseline,
        {**baseline, "retryable": True},
    ) == ["telecraft.client.UpdatesRecoveryExhaustedError: retryable changed from False to True"]


def test_stable_api__symbol_constructor_uses_signature_compatibility_rules() -> None:
    current = build_snapshot(
        matrix_path=MATRIX_PATH,
        release=__version__,
        source_ref="working-tree",
        source_commit="0" * 40,
        source_tree="0" * 40,
    )["symbols"]["telecraft.client.UpdatesRecoveryExhaustedError"]
    baseline = json.loads(json.dumps(current))
    additive = json.loads(json.dumps(current))
    additive["constructor"]["parameters"].append(
        {
            "name": "diagnostic",
            "kind": "KEYWORD_ONLY",
            "annotation": "str | None",
            "has_default": True,
            "default_repr": "None",
        }
    )
    regressed = json.loads(json.dumps(current))
    regressed["constructor"]["parameters"] = [
        parameter
        for parameter in regressed["constructor"]["parameters"]
        if parameter["name"] != "attempts"
    ]

    name = "telecraft.client.UpdatesRecoveryExhaustedError"
    assert _symbol_errors(name, baseline, additive) == []
    assert f"{name}.__init__: removed parameter 'attempts'" in _symbol_errors(
        name,
        baseline,
        regressed,
    )


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

        current_symbols = current["symbols"]
        for name, old_contract in baseline.get("symbols", {}).items():
            new_contract = current_symbols.get(name)
            if new_contract is None:
                baseline_errors.append(f"{name}: released public symbol was removed")
                continue
            baseline_errors.extend(_symbol_errors(name, old_contract, new_contract))

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
