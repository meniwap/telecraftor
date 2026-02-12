from __future__ import annotations

from telecraft.client import (
    GroupCallJoinParams,
    GroupCallRef,
    ReportReasonBuilder,
    TakeoutScopes,
    ThemeRef,
    WallpaperRef,
)


def test_ref_builders__theme_ref_slug__returns_expected_shape() -> None:
    ref = ThemeRef.slug("night")
    assert ref.slug_value == "night"


def test_ref_builders__wallpaper_ref_slug__returns_expected_shape() -> None:
    ref = WallpaperRef.slug("blue")
    assert ref.slug_value == "blue"


def test_ref_builders__group_call_ref_from_parts__returns_expected_shape() -> None:
    ref = GroupCallRef.from_parts(1, 2)
    assert ref.call_id == 1 and ref.access_hash == 2


def test_ref_builders__group_call_join_params_from_dict__returns_expected_shape() -> None:
    params = GroupCallJoinParams.from_dict({"v": 1})
    assert "v" in params.data


def test_ref_builders__takeout_scopes__returns_expected_shape() -> None:
    scopes = TakeoutScopes(files=False)
    assert scopes.files is False


def test_ref_builders__report_reason_builder_other__returns_expected_shape() -> None:
    reason = ReportReasonBuilder.other("x")
    assert reason is not None
