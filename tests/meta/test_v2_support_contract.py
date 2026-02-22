from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tests.meta.test_v2_method_coverage import MethodRef, _load_matrix

CONTRACT_PATH = Path("tests/meta/v2_support_contract.json")
ALLOWED_SUPPORT_TIER = {"A", "B", "experimental"}
ALLOWED_COMPAT = {"additive+deprecation", "best_effort"}
ALLOWED_LIVE_GATE = {"prod_safe", "none"}


def _load_contract() -> dict[str, Any]:
    data = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise AssertionError("support contract must be a top-level object")
    return data


def _resolve_support(row: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    namespace = str(row["namespace"])
    method = str(row["method"])
    stability = str(row["stability"])
    defaults = contract["defaults"]
    namespace_overrides = contract["namespace_overrides"]
    method_overrides = contract["method_overrides"]

    method_key = f"{namespace}.{method}"
    if method_key in method_overrides:
        resolved = method_overrides[method_key]
    elif namespace in namespace_overrides:
        resolved = namespace_overrides[namespace]
    else:
        resolved = defaults[stability]

    assert isinstance(resolved, dict)
    return resolved


def test_support_contract__every_matrix_method_resolves_support_tier() -> None:
    contract = _load_contract()
    matrix = _load_matrix()

    assert contract.get("version") == 1
    for key in ("defaults", "namespace_overrides", "method_overrides"):
        assert isinstance(contract.get(key), dict), f"{key} must be an object"

    defaults = contract["defaults"]
    assert set(defaults) == {"stable", "experimental"}

    for policy in defaults.values():
        assert isinstance(policy, dict)
        assert policy.get("support_tier") in ALLOWED_SUPPORT_TIER
        assert policy.get("compat") in ALLOWED_COMPAT
        assert policy.get("live_gate") in ALLOWED_LIVE_GATE

    for row in matrix:
        resolved = _resolve_support(row, contract)
        assert resolved.get("support_tier") in ALLOWED_SUPPORT_TIER
        assert resolved.get("compat") in ALLOWED_COMPAT
        assert resolved.get("live_gate") in ALLOWED_LIVE_GATE


def test_support_contract__tier_a_requires_stable_methods() -> None:
    contract = _load_contract()
    matrix = _load_matrix()

    offenders: list[str] = []
    for row in matrix:
        resolved = _resolve_support(row, contract)
        if resolved.get("support_tier") != "A":
            continue
        if row["stability"] != "stable":
            offenders.append(f"{row['namespace']}.{row['method']}")

    assert not offenders, f"Tier A methods must be stable: {offenders}"


def test_support_contract__experimental_defaults_to_experimental_support() -> None:
    contract = _load_contract()
    matrix = _load_matrix()

    defaults = contract["defaults"]
    namespace_overrides = contract["namespace_overrides"]
    method_overrides = contract["method_overrides"]

    checked = 0
    for row in matrix:
        if row["stability"] != "experimental":
            continue
        namespace = str(row["namespace"])
        method_key = f"{namespace}.{row['method']}"
        if namespace in namespace_overrides or method_key in method_overrides:
            continue
        resolved = _resolve_support(row, contract)
        assert resolved["support_tier"] == defaults["experimental"]["support_tier"]
        assert resolved["support_tier"] == "experimental"
        checked += 1

    assert checked > 0, "expected at least one experimental method using default policy"


def test_support_contract__overrides_reference_existing_methods() -> None:
    contract = _load_contract()
    matrix = _load_matrix()

    refs = {MethodRef(namespace=str(r["namespace"]), method=str(r["method"])) for r in matrix}
    namespaces = {ref.namespace for ref in refs}

    unknown_namespaces = sorted(set(contract["namespace_overrides"]) - namespaces)
    assert not unknown_namespaces, f"Unknown namespace overrides: {unknown_namespaces}"

    unknown_methods: list[str] = []
    for key in contract["method_overrides"]:
        if not isinstance(key, str) or "." not in key:
            unknown_methods.append(str(key))
            continue
        namespace, method = key.rsplit(".", 1)
        if MethodRef(namespace=namespace, method=method) not in refs:
            unknown_methods.append(key)

    assert not unknown_methods, f"Unknown method overrides: {unknown_methods}"
