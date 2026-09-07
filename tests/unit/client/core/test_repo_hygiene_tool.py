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
        "src/telecraft/.DS_Store",
        "src/telecraft/.env.production",
        "src/telecraft/operator.env",
        "src/telecraft/session.json",
        "src/telecraft/prod.session",
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


def test_repo_hygiene__artifacts_require_legacy_runtime_and_typing_members(
    tmp_path, monkeypatch
) -> None:
    mod = _load_hygiene_module()
    wheel = tmp_path / "telecraft-0.2.3-py3-none-any.whl"
    sdist = tmp_path / "telecraft-0.2.3.tar.gz"
    wheel.touch()
    sdist.touch()

    expected_by_name = {
        wheel.name: mod.REQUIRED_WHEEL_MEMBERS,
        sdist.name: mod.REQUIRED_SDIST_MEMBERS,
    }
    monkeypatch.setattr(
        mod,
        "_artifact_members",
        lambda artifact: sorted(expected_by_name[artifact.name]),
    )

    assert mod._check_artifacts([wheel, sdist]) == []


def test_repo_hygiene__artifacts_fail_when_required_member_is_missing(
    tmp_path, monkeypatch
) -> None:
    mod = _load_hygiene_module()
    wheel = tmp_path / "telecraft-0.2.3-py3-none-any.whl"
    sdist = tmp_path / "telecraft-0.2.3.tar.gz"
    wheel.touch()
    sdist.touch()
    missing_wheel = "telecraft/tl/generated/_legacy_types.py"
    missing_sdist = "src/telecraft/schema/sources/legacy_provenance.json"
    members_by_name = {
        wheel.name: mod.REQUIRED_WHEEL_MEMBERS - {missing_wheel},
        sdist.name: mod.REQUIRED_SDIST_MEMBERS - {missing_sdist},
    }
    monkeypatch.setattr(
        mod,
        "_artifact_members",
        lambda artifact: sorted(members_by_name[artifact.name]),
    )

    assert mod._check_artifacts([wheel, sdist]) == [
        f"{wheel.name}:{missing_wheel}: required package member is missing",
        f"{sdist.name}:{missing_sdist}: required package member is missing",
    ]


def test_repo_hygiene__history_record_may_name_exact_purge_paths(tmp_path, monkeypatch) -> None:
    mod = _load_hygiene_module()
    record = tmp_path / "docs" / "20_history_cleanup_record.md"
    record.parent.mkdir(parents=True)
    manual_labs = "apps/" + "manual_labs"
    streaming_bot = "apps/" + "streamingbot"
    record.write_text(f"Removed {manual_labs} and {streaming_bot}.\n", encoding="utf-8")
    monkeypatch.setattr(mod, "ROOT", tmp_path)

    assert mod._check_references(["docs/20_history_cleanup_record.md"]) == []


def test_repo_hygiene__history_paths_parse_reachable_objects(monkeypatch) -> None:
    mod = _load_hygiene_module()

    class Result:
        stdout = (
            "a" * 40 + "\n"
            "b" * 40 + " reports/live/capture.json\n"
            "c" * 40 + " src/telecraft/client/client.py\n"
            "d" * 40 + " reports/live/capture.json\n"
        )

    monkeypatch.setattr(mod.subprocess, "run", lambda *args, **kwargs: Result())

    assert mod._git_history_paths() == [
        "reports/live/capture.json",
        "src/telecraft/client/client.py",
    ]
    errors = mod._check_tracked_paths(mod._git_history_paths())
    assert errors == ["reports/live/capture.json: forbidden tracked path under reports/"]
