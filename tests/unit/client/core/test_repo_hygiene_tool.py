from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_hygiene_module():
    path = Path("tools/check_repo_hygiene.py")
    spec = importlib.util.spec_from_file_location("telecraft_tools_check_repo_hygiene", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_repo_hygiene__blocks_private_planning_files() -> None:
    mod = _load_hygiene_module()

    assert mod._forbidden_tracked_reason(".telecraft/production_roadmap.md")
    assert mod._forbidden_artifact_reason(".telecraft/production_roadmap.md")


def test_repo_hygiene__blocks_runtime_secret_and_cache_paths() -> None:
    mod = _load_hygiene_module()

    forbidden = [
        ".sessions/prod/prod_dc2.session.json",
        "apps/env.sh",
        "downloads/photo.jpg",
        "reports/live/prod/run/artifacts.json",
        "src/telecraft/__pycache__/client.pyc",
        ".pytest_cache/v/cache/nodeids",
    ]

    for path in forbidden:
        assert mod._forbidden_tracked_reason(path), path
        assert mod._forbidden_artifact_reason(path), path
