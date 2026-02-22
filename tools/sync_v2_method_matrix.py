from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.meta.test_v2_method_coverage import MethodRef, _discover_v2_methods

MATRIX_PATH = Path("tests/meta/v2_method_matrix.yaml")
DEFAULT_SCENARIOS = [
    "delegates_to_raw",
    "passes_timeout",
    "forwards_args",
    "returns_expected_shape",
    "handles_rpc_error",
]


@dataclass(frozen=True)
class MatrixRow:
    namespace: str
    method: str
    stability: str
    tier: str
    requires_second_account: bool
    required_scenarios: list[str]
    introduced_in: str
    deprecation_target: None


def _load_rows(path: Path) -> list[dict[str, Any]]:
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, list):
        raise ValueError("matrix must be a top-level list")
    return data


def _existing_refs(rows: list[dict[str, Any]]) -> set[MethodRef]:
    refs: set[MethodRef] = set()
    for row in rows:
        namespace = row.get("namespace")
        method = row.get("method")
        if isinstance(namespace, str) and isinstance(method, str):
            refs.add(MethodRef(namespace=namespace, method=method))
    return refs


def _new_row(ref: MethodRef, *, introduced_in: str, stability: str, tier: str) -> dict[str, Any]:
    row = MatrixRow(
        namespace=ref.namespace,
        method=ref.method,
        stability=stability,
        tier=tier,
        requires_second_account=False,
        required_scenarios=list(DEFAULT_SCENARIOS),
        introduced_in=introduced_in,
        deprecation_target=None,
    )
    return asdict(row)


def _write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        json.dumps(rows, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Add missing V2 methods to tests/meta/v2_method_matrix.yaml."
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=MATRIX_PATH,
        help="Path to method matrix JSON file.",
    )
    parser.add_argument(
        "--introduced-in",
        type=str,
        default="v4.next",
        help="Default introduced_in value for newly generated rows.",
    )
    parser.add_argument(
        "--stability",
        choices=("stable", "experimental"),
        default="stable",
        help="Default stability for newly generated rows.",
    )
    parser.add_argument(
        "--tier",
        choices=("unit", "live_core", "live_second_account", "live_optional"),
        default="unit",
        help="Default test tier for newly generated rows.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if missing rows exist; do not write.",
    )
    args = parser.parse_args()

    rows = _load_rows(args.path)
    discovered = _discover_v2_methods()
    existing = _existing_refs(rows)

    missing = sorted(discovered - existing, key=lambda x: (x.namespace, x.method))
    if not missing:
        print("v2 matrix is up to date")
        return 0

    if args.check:
        print("Missing matrix rows:")
        for ref in missing:
            print(f"- {ref.namespace}.{ref.method}")
        return 1

    generated = [
        _new_row(
            ref,
            introduced_in=args.introduced_in,
            stability=args.stability,
            tier=args.tier,
        )
        for ref in missing
    ]
    updated = rows + generated
    _write_rows(args.path, updated)

    print(f"added {len(generated)} rows to {args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
