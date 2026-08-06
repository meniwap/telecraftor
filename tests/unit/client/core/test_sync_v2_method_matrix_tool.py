from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


def _load_sync_module() -> Any:
    path = Path(__file__).resolve().parents[4] / "tools" / "sync_v2_method_matrix.py"
    spec = importlib.util.spec_from_file_location("telecraft_sync_v2_method_matrix", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_sync_method_matrix__new_methods_default_to_experimental(
    monkeypatch, tmp_path: Path
) -> None:
    module = _load_sync_module()
    path = tmp_path / "matrix.json"
    path.write_text("[]\n", encoding="utf-8")
    missing = module.MethodRef(namespace="new_namespace", method="new_method")
    monkeypatch.setattr(module, "_discover_v2_methods", lambda: {missing})
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "sync_v2_method_matrix.py",
            "--path",
            str(path),
            "--introduced-in",
            "0.2.2",
        ],
    )

    assert module.main() == 0
    rows = json.loads(path.read_text(encoding="utf-8"))
    assert rows == [
        {
            "namespace": "new_namespace",
            "method": "new_method",
            "stability": "experimental",
            "tier": "unsupported_or_experimental",
            "requires_second_account": False,
            "required_scenarios": [
                "delegates_to_raw",
                "passes_timeout",
                "forwards_args",
                "returns_expected_shape",
                "handles_rpc_error",
            ],
            "introduced_in": "0.2.2",
            "deprecation_target": None,
        }
    ]
