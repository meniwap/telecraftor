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
        "tests/unit/fixtures/tl/live_capture.bin",
        "src/telecraft/__pycache__/client.pyc",
        ".pytest_cache/v/cache/nodeids",
    ]

    for path in forbidden:
        assert mod._forbidden_tracked_reason(path), path
        assert mod._forbidden_artifact_reason(path), path


def test_repo_hygiene__artifact_allow_list_is_fail_closed() -> None:
    mod = _load_hygiene_module()

    wheel = Path("dist/telecraft-0.2.0-py3-none-any.whl")
    sdist = Path("dist/telecraft-0.2.0.tar.gz")

    assert mod._unexpected_artifact_member_reason(wheel, "telecraft/client/client.py") is None
    assert (
        mod._unexpected_artifact_member_reason(
            wheel,
            "telecraft-0.2.0.dist-info/METADATA",
        )
        is None
    )
    assert mod._unexpected_artifact_member_reason(sdist, "src/telecraft/client/client.py") is None
    assert mod._unexpected_artifact_member_reason(sdist, "README.md") is None
    assert mod._unexpected_artifact_member_reason(sdist, ".gitignore") is None

    assert mod._unexpected_artifact_member_reason(wheel, "tests/test_private.py")
    assert mod._unexpected_artifact_member_reason(sdist, ".github/workflows/publish.yml")
    assert mod._unexpected_artifact_member_reason(sdist, "apps/env.sh")
