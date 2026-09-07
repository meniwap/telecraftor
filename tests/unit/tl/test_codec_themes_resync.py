from __future__ import annotations

import pytest

from telecraft.tl.codec import (
    VECTOR_CONSTRUCTOR_ID,
    TLWriter,
    UnknownConstructorError,
    loads,
)
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


def test_codec__account_themes__unknown_nested_object_is_not_skipped() -> None:
    writer = TLWriter()
    _write_account_themes_prefix(writer, count=2)
    writer.write_int(_UNKNOWN_THEME_CONSTRUCTOR_ID)
    writer.write_int(0x10203040)  # synthetic bytes skipped during resync
    writer.write_object(_synthetic_theme(theme_id=1))
    with pytest.raises(UnknownConstructorError) as caught:
        loads(writer.to_bytes())

    assert caught.value.constructor_id == _UNKNOWN_THEME_CONSTRUCTOR_ID
    assert caught.value.expected_type == "Theme"
    assert caught.value.path.endswith("account.themes.themes[0]")


def test_codec__unknown_nested_object_aborts_the_whole_rpc_result() -> None:
    writer = TLWriter()
    writer.write_int(_RPC_RESULT_CONSTRUCTOR_ID)
    writer.write_long(987654321)
    _write_account_themes_prefix(writer, count=2)
    writer.write_object(_synthetic_theme(theme_id=2))
    writer.write_int(_UNKNOWN_THEME_CONSTRUCTOR_ID)
    writer.write_bytes(b"synthetic trailing entry")
    with pytest.raises(UnknownConstructorError) as caught:
        loads(writer.to_bytes())

    assert caught.value.constructor_id == _UNKNOWN_THEME_CONSTRUCTOR_ID
    assert caught.value.expected_type == "Theme"
    assert "rpc_result" in caught.value.path
