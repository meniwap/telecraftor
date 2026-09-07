from __future__ import annotations

import argparse
import inspect
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = os.environ.get("TELECRAFT_SNAPSHOT_SOURCE", str(ROOT / "src"))
if SOURCE_PATH not in sys.path:
    sys.path.insert(0, SOURCE_PATH)

from telecraft.client import UpdatesRecoveryExhaustedError  # noqa: E402
from telecraft.client.client import Client  # noqa: E402
from telecraft.client.mtproto import ClientInit, MtprotoClient  # noqa: E402

PUBLIC_CONSTRUCTORS = {
    "telecraft.client.Client": Client,
    "telecraft.client.ClientInit": ClientInit,
    "telecraft.client.mtproto.MtprotoClient": MtprotoClient,
}
PUBLIC_SYMBOLS = {
    "telecraft.client.UpdatesRecoveryExhaustedError": UpdatesRecoveryExhaustedError,
}
DYNAMIC_DEFAULTS = ("telecraft.client.ClientInit.app_version",)


def _is_public_callable(value: Any) -> bool:
    return (
        inspect.iscoroutinefunction(value)
        or inspect.isasyncgenfunction(value)
        or inspect.isfunction(value)
        or inspect.ismethod(value)
    )


def discover_public_callables() -> dict[str, Any]:
    """Discover the public facade exactly as a client user reaches it."""

    callables: dict[str, Any] = {}
    visited: set[int] = set()
    client = Client(raw=object())  # type: ignore[arg-type]

    def add(name: str, value: Any) -> None:
        previous = callables.setdefault(name, value)
        if previous is not value and inspect.signature(previous) != inspect.signature(value):
            raise RuntimeError(f"conflicting public callables at {name}")

    def visit(obj: Any, namespace: str) -> None:
        if id(obj) in visited:
            return
        visited.add(id(obj))

        for method, declared in inspect.getmembers(type(obj)):
            if method.startswith("_") or not _is_public_callable(declared):
                continue
            add(f"{namespace}.{method}", getattr(obj, method))

        for name, nested in vars(obj).items():
            if name.startswith("_") or name == "raw":
                continue
            if not type(nested).__module__.startswith("telecraft.client.apis."):
                continue

            declared = getattr(type(obj), name, None)
            call = getattr(type(nested), "__call__", None)
            if _is_public_callable(call) and not _is_public_callable(declared):
                add(f"{namespace}.{name}", nested)

            child_namespace = name if namespace == "client" else f"{namespace}.{name}"
            visit(nested, child_namespace)

    visit(client, "client")
    return callables


def _annotation_text(annotation: Any) -> str | None:
    if annotation is inspect.Signature.empty:
        return None
    if isinstance(annotation, str):
        return annotation
    return inspect.formatannotation(annotation)


def _parameter_record(parameter: inspect.Parameter) -> dict[str, Any]:
    has_default = parameter.default is not inspect.Parameter.empty
    return {
        "name": parameter.name,
        "kind": parameter.kind.name,
        "annotation": _annotation_text(parameter.annotation),
        "has_default": has_default,
        "default_repr": repr(parameter.default) if has_default else None,
    }


def _signature_record(value: Any) -> dict[str, Any]:
    signature = inspect.signature(value)
    return {
        "parameters": [_parameter_record(item) for item in signature.parameters.values()],
        "return_annotation": _annotation_text(signature.return_annotation),
    }


def _symbol_record(value: Any) -> dict[str, Any]:
    if not inspect.isclass(value):
        raise TypeError(f"stable public symbol must be a class, got {value!r}")
    return {
        "kind": "class",
        "module": value.__module__,
        "qualname": value.__qualname__,
        "is_exception": issubclass(value, Exception),
        "retryable": getattr(value, "retryable", None),
        "constructor": _signature_record(value),
    }


def build_snapshot(
    *,
    matrix_path: Path,
    release: str,
    source_ref: str,
    source_commit: str,
    source_tree: str,
) -> dict[str, Any]:
    rows = json.loads(matrix_path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("method matrix must contain a top-level list")

    callables = discover_public_callables()
    methods: dict[str, Any] = {}
    for row in rows:
        if row.get("stability") != "stable":
            continue
        namespace = row.get("namespace")
        method = row.get("method")
        if not isinstance(namespace, str) or not isinstance(method, str):
            raise ValueError("stable matrix rows require string namespace and method fields")
        public_name = f"{namespace}.{method}"
        try:
            value = callables[public_name]
        except KeyError as exc:
            raise ValueError(f"stable matrix method is not public: {public_name}") from exc
        methods[public_name] = _signature_record(value)

    return {
        "schema_version": 2,
        "release": release,
        "source_ref": source_ref,
        "source_commit": source_commit,
        "source_tree": source_tree,
        "dynamic_defaults": list(DYNAMIC_DEFAULTS),
        "constructors": {
            name: _signature_record(value) for name, value in sorted(PUBLIC_CONSTRUCTORS.items())
        },
        "symbols": {name: _symbol_record(value) for name, value in sorted(PUBLIC_SYMBOLS.items())},
        "methods": dict(sorted(methods.items())),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Snapshot Telecraft's stable public API.")
    parser.add_argument("--matrix", type=Path, default=Path("tests/meta/v2_method_matrix.yaml"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--release", required=True)
    parser.add_argument("--source-ref", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--source-tree", required=True)
    args = parser.parse_args()

    snapshot = build_snapshot(
        matrix_path=args.matrix,
        release=args.release,
        source_ref=args.source_ref,
        source_commit=args.source_commit,
        source_tree=args.source_tree,
    )
    args.output.write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"wrote {len(snapshot['methods'])} stable methods to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
