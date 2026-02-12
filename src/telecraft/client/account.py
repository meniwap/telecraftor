from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from telecraft.tl.generated.types import (
    InputTheme,
    InputThemeSlug,
    InputWallPaper,
    InputWallPaperNoFile,
    InputWallPaperSlug,
)

ThemeRefKind = Literal["id", "slug"]
WallpaperRefKind = Literal["id", "slug", "no_file"]


@dataclass(frozen=True, slots=True)
class AuthorizationRef:
    hash: int

    @classmethod
    def from_hash(cls, hash: int) -> AuthorizationRef:
        return cls(hash=int(hash))


@dataclass(frozen=True, slots=True)
class WebAuthorizationRef:
    hash: int

    @classmethod
    def from_hash(cls, hash: int) -> WebAuthorizationRef:
        return cls(hash=int(hash))


@dataclass(frozen=True, slots=True)
class ThemeRef:
    kind: ThemeRefKind
    theme_id: int | None = None
    access_hash: int | None = None
    slug_value: str | None = None

    @classmethod
    def by_id(cls, theme_id: int, access_hash: int) -> ThemeRef:
        return cls(kind="id", theme_id=int(theme_id), access_hash=int(access_hash))

    @classmethod
    def slug(cls, slug: str) -> ThemeRef:
        value = str(slug).strip()
        if not value:
            raise ValueError("slug cannot be empty")
        return cls(kind="slug", slug_value=value)


@dataclass(frozen=True, slots=True)
class WallpaperRef:
    kind: WallpaperRefKind
    wall_id: int | None = None
    access_hash: int | None = None
    slug_value: str | None = None

    @classmethod
    def by_id(cls, wall_id: int, access_hash: int) -> WallpaperRef:
        return cls(kind="id", wall_id=int(wall_id), access_hash=int(access_hash))

    @classmethod
    def slug(cls, slug: str) -> WallpaperRef:
        value = str(slug).strip()
        if not value:
            raise ValueError("slug cannot be empty")
        return cls(kind="slug", slug_value=value)

    @classmethod
    def no_file(cls, wall_id: int) -> WallpaperRef:
        return cls(kind="no_file", wall_id=int(wall_id))


def build_input_theme(ref: ThemeRef | Any) -> Any:
    if not isinstance(ref, ThemeRef):
        return ref
    if ref.kind == "id":
        if ref.theme_id is None or ref.access_hash is None:
            raise ValueError("ThemeRef.by_id requires theme_id and access_hash")
        return InputTheme(id=int(ref.theme_id), access_hash=int(ref.access_hash))
    if ref.kind == "slug":
        if not ref.slug_value:
            raise ValueError("ThemeRef.slug requires slug")
        return InputThemeSlug(slug=str(ref.slug_value))
    raise ValueError(f"Unsupported ThemeRef kind: {ref.kind!r}")


def build_input_wallpaper(ref: WallpaperRef | Any) -> Any:
    if not isinstance(ref, WallpaperRef):
        return ref
    if ref.kind == "id":
        if ref.wall_id is None or ref.access_hash is None:
            raise ValueError("WallpaperRef.by_id requires wall_id and access_hash")
        return InputWallPaper(id=int(ref.wall_id), access_hash=int(ref.access_hash))
    if ref.kind == "slug":
        if not ref.slug_value:
            raise ValueError("WallpaperRef.slug requires slug")
        return InputWallPaperSlug(slug=str(ref.slug_value))
    if ref.kind == "no_file":
        if ref.wall_id is None:
            raise ValueError("WallpaperRef.no_file requires wall_id")
        return InputWallPaperNoFile(id=int(ref.wall_id))
    raise ValueError(f"Unsupported WallpaperRef kind: {ref.kind!r}")
