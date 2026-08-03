from __future__ import annotations

import ast
import importlib.util
import inspect
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from telecraft.client.client import Client

MATRIX_PATH = Path("tests/meta/v2_method_matrix.yaml")
ALLOWED_STABILITY = {"experimental", "stable"}
ALLOWED_TIER = {
    "unit",
    "manual_live_optional",
    "external_manual",
    "unsupported_or_experimental",
}
SCENARIOS_STABLE_UNIT_MIN = {
    "delegates_to_raw",
    "forwards_args",
    "returns_expected_shape",
    "handles_rpc_error",
}
TEST_DIRS_FOR_NAMING = (Path("tests/unit/client/v2"),)
NAME_RE = re.compile(r"^test_[a-z0-9_]+__[a-z0-9_]+__[a-z0-9_]+$")


@dataclass(frozen=True)
class MethodRef:
    namespace: str
    method: str


SYNCHRONOUS_HELPERS = {MethodRef(namespace="notifications", method="peer")}
SCENARIOS_STABLE_SYNC_MIN = {"forwards_args", "returns_expected_shape"}


def _normalize_token(token: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", token.lower()).strip("_")


def _scenario_test_name(namespace: str, method: str, scenario: str) -> str:
    ns = _normalize_token(namespace)
    meth = _normalize_token(method)
    scen = _normalize_token(scenario)
    return f"test_{ns}__{meth}__{scen}"


def _is_public_callable(value: Any) -> bool:
    return (
        inspect.iscoroutinefunction(value)
        or inspect.isasyncgenfunction(value)
        or inspect.isfunction(value)
        or inspect.ismethod(value)
    )


def _discover_v2_callables() -> dict[MethodRef, Any]:
    """Discover the facade exactly as users reach it at runtime."""

    refs: dict[MethodRef, Any] = {}
    visited: set[int] = set()
    client = Client(raw=object())  # type: ignore[arg-type]

    def add(ref: MethodRef, value: Any) -> None:
        previous = refs.setdefault(ref, value)
        assert previous is value or inspect.signature(previous) == inspect.signature(value), (
            f"Conflicting public callables at {ref.namespace}.{ref.method}"
        )

    def visit(obj: Any, namespace: str) -> None:
        if id(obj) in visited:
            return
        visited.add(id(obj))

        for name, declared in inspect.getmembers(type(obj)):
            if name.startswith("_") or not _is_public_callable(declared):
                continue
            add(MethodRef(namespace=namespace, method=name), getattr(obj, name))

        for name, nested in vars(obj).items():
            if name.startswith("_") or name == "raw":
                continue
            if not type(nested).__module__.startswith("telecraft.client.apis."):
                continue

            # Callable namespace objects are normally mirrored by a method on
            # their parent (for example ``channels.search_posts(...)``). If a
            # future namespace omits that alias, still track the callable path.
            declared = getattr(type(obj), name, None)
            call = getattr(type(nested), "__call__", None)
            if _is_public_callable(call) and not _is_public_callable(declared):
                add(MethodRef(namespace=namespace, method=name), nested)

            child_namespace = name if namespace == "client" else f"{namespace}.{name}"
            visit(nested, child_namespace)

    visit(client, "client")
    return refs


def _discover_v2_methods() -> set[MethodRef]:
    return set(_discover_v2_callables())


def _discover_timeout_support() -> dict[MethodRef, bool]:
    return {
        ref: "timeout" in inspect.signature(fn).parameters
        for ref, fn in _discover_v2_callables().items()
    }


def _load_matrix() -> list[dict[str, Any]]:
    raw = MATRIX_PATH.read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, list):
        raise AssertionError("v2_method_matrix.yaml must contain a top-level list")
    return data


def _load_module_from_path(path: Path) -> Any:
    module_name = "telecraft_test_" + re.sub(r"[^a-zA-Z0-9]+", "_", str(path))
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Unable to load test module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _discover_test_function_names() -> set[str]:
    names: set[str] = set()
    for test_dir in TEST_DIRS_FOR_NAMING:
        if not test_dir.exists():
            continue
        for path in sorted(test_dir.rglob("test_*.py")):
            if path.name == "test_v2_wrapper_contracts.py":
                module = _load_module_from_path(path)
                for name, obj in inspect.getmembers(module):
                    if not name.startswith("test_"):
                        continue
                    if inspect.isfunction(obj) or inspect.iscoroutinefunction(obj):
                        names.add(name)
                continue

            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in tree.body:
                if isinstance(
                    node, (ast.FunctionDef, ast.AsyncFunctionDef)
                ) and node.name.startswith("test_"):
                    names.add(node.name)
    return names


def test_v2_method_matrix_is_complete_and_valid() -> None:
    methods = _discover_v2_methods()
    timeout_support = _discover_timeout_support()
    matrix = _load_matrix()

    seen: set[MethodRef] = set()
    for row in matrix:
        namespace = row.get("namespace")
        method = row.get("method")
        stability = row.get("stability")
        tier = row.get("tier")
        required_scenarios = row.get("required_scenarios")

        assert isinstance(namespace, str) and namespace
        assert isinstance(method, str) and method
        assert stability in ALLOWED_STABILITY
        assert tier in ALLOWED_TIER
        assert isinstance(required_scenarios, list) and required_scenarios
        assert all(isinstance(x, str) and x for x in required_scenarios)

        ref = MethodRef(namespace=namespace, method=method)
        assert ref not in seen, f"Duplicate matrix row: {namespace}.{method}"
        seen.add(ref)

        if stability == "stable" and tier == "unit":
            if ref in SYNCHRONOUS_HELPERS:
                expected = set(SCENARIOS_STABLE_SYNC_MIN)
            else:
                expected = set(SCENARIOS_STABLE_UNIT_MIN)
                if timeout_support.get(ref, False):
                    expected.add("passes_timeout")
            assert expected.issubset(set(required_scenarios)), (
                f"{namespace}.{method} must include stable minimum scenarios"
            )

    missing = sorted(methods - seen, key=lambda x: (x.namespace, x.method))
    extra = sorted(seen - methods, key=lambda x: (x.namespace, x.method))
    assert not missing, f"Missing matrix entries: {[f'{m.namespace}.{m.method}' for m in missing]}"
    assert not extra, (
        f"Matrix has non-existing methods: {[f'{m.namespace}.{m.method}' for m in extra]}"
    )


def test_v2_required_scenarios_have_named_tests() -> None:
    matrix = _load_matrix()
    discovered_names = _discover_test_function_names()

    missing: list[str] = []
    for row in matrix:
        if row["tier"] != "unit":
            continue
        namespace = str(row["namespace"])
        method = str(row["method"])
        for scenario in row["required_scenarios"]:
            expected = _scenario_test_name(namespace, method, str(scenario))
            if expected not in discovered_names:
                missing.append(expected)

    assert not missing, "Missing required scenario tests (name-based coverage gate):\n" + "\n".join(
        f"- {name}" for name in sorted(missing)
    )


def test_v2_test_names_follow_convention() -> None:
    violations: list[str] = []
    for name in sorted(_discover_test_function_names()):
        if not NAME_RE.match(name):
            violations.append(name)

    assert not violations, (
        "Test name convention violations. Expected: test_<namespace>__<method>__<scenario>\n"
        + "\n".join(f"- {v}" for v in violations)
    )
