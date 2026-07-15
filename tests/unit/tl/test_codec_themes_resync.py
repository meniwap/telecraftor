from __future__ import annotations

from telecraft.tl.codec import VECTOR_CONSTRUCTOR_ID, RpcResult, TLWriter, UnknownTLObject, loads
from telecraft.tl.generated.types import AccountThemes, Theme

_RPC_RESULT_CONSTRUCTOR_ID = -212046591
_UNKNOWN_THEME_CONSTRUCTOR_ID = 0x12345678


def _synthetic_theme(*, theme_id: int) -> Theme:
    return Theme(
        flags=0,
        creator=False,
        default=False,
        for_chat=False,
        id=theme_id,
        access_hash=theme_id + 100,
        slug=f"synthetic-{theme_id}",
        title=f"Synthetic theme {theme_id}",
        document=None,
        settings=None,
        emoticon=None,
        installs_count=None,
    )


def _write_account_themes_prefix(writer: TLWriter, *, count: int) -> None:
    writer.write_int(AccountThemes.TL_ID)
    writer.write_long(123)
    writer.write_int(VECTOR_CONSTRUCTOR_ID)
    writer.write_int(count)


def test_codec__account_themes__resync_and_unknown_entry_instead_of_crash() -> None:
    writer = TLWriter()
    _write_account_themes_prefix(writer, count=2)
    writer.write_int(_UNKNOWN_THEME_CONSTRUCTOR_ID)
    writer.write_int(0x10203040)  # synthetic bytes skipped during resync
    writer.write_object(_synthetic_theme(theme_id=1))
    decoded = loads(writer.to_bytes())

    assert getattr(decoded, "TL_NAME", "") == "account.themes"
    unknown_entries = [x for x in decoded.themes if isinstance(x, UnknownTLObject)]

    assert len(unknown_entries) == 1
    assert len(decoded.themes) == 2
    assert all(entry.expected_type == "Theme" for entry in unknown_entries)
    assert all(entry.raw for entry in unknown_entries)
    assert getattr(decoded.themes[1], "title", b"") == b"Synthetic theme 1"


def test_codec__account_themes__returns_usable_vector_with_unknown_objects() -> None:
    writer = TLWriter()
    writer.write_int(_RPC_RESULT_CONSTRUCTOR_ID)
    writer.write_long(987654321)
    _write_account_themes_prefix(writer, count=2)
    writer.write_object(_synthetic_theme(theme_id=2))
    writer.write_int(_UNKNOWN_THEME_CONSTRUCTOR_ID)
    writer.write_bytes(b"synthetic trailing entry")
    wrapped = loads(writer.to_bytes())

    assert isinstance(wrapped, RpcResult)
    assert getattr(wrapped.result, "TL_NAME", "") == "account.themes"

    themes = list(getattr(wrapped.result, "themes", []))
    assert themes
    assert any(getattr(item, "TL_NAME", "") == "theme" for item in themes)
    assert any(isinstance(item, UnknownTLObject) for item in themes)
