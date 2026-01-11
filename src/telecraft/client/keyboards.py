"""
Keyboard builders for Telegram bots.

Provides easy-to-use builders for creating inline and reply keyboards.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from telecraft.tl.generated.types import (
    KeyboardButton,
    KeyboardButtonCallback,
    KeyboardButtonCopy,
    KeyboardButtonRequestGeoLocation,
    KeyboardButtonRequestPhone,
    KeyboardButtonRow,
    KeyboardButtonSwitchInline,
    KeyboardButtonUrl,
    KeyboardButtonWebView,
    ReplyInlineMarkup,
    ReplyKeyboardForceReply,
    ReplyKeyboardHide,
    ReplyKeyboardMarkup,
)


# ========================== Inline Keyboard ==========================


@dataclass
class InlineButton:
    """Helper class to create inline keyboard buttons."""

    text: str
    callback_data: bytes | None = None
    url: str | None = None
    switch_inline_query: str | None = None
    switch_inline_query_current_chat: str | None = None
    web_app_url: str | None = None
    copy_text: str | None = None

    def to_tl(self) -> Any:
        """Convert to TL object."""
        if self.callback_data is not None:
            return KeyboardButtonCallback(
                flags=0,
                requires_password=None,
                text=self.text,
                data=self.callback_data,
            )
        if self.url is not None:
            return KeyboardButtonUrl(text=self.text, url=self.url)
        if self.switch_inline_query is not None:
            return KeyboardButtonSwitchInline(
                flags=0,
                same_peer=None,
                text=self.text,
                query=self.switch_inline_query,
                peer_types=None,
            )
        if self.switch_inline_query_current_chat is not None:
            return KeyboardButtonSwitchInline(
                flags=1,  # same_peer flag
                same_peer=True,
                text=self.text,
                query=self.switch_inline_query_current_chat,
                peer_types=None,
            )
        if self.web_app_url is not None:
            return KeyboardButtonWebView(text=self.text, url=self.web_app_url)
        if self.copy_text is not None:
            return KeyboardButtonCopy(text=self.text, copy_text=self.copy_text)
        # Default to callback with empty data
        return KeyboardButtonCallback(
            flags=0,
            requires_password=None,
            text=self.text,
            data=b"",
        )


@dataclass
class InlineKeyboard:
    """
    Builder for inline keyboards (buttons attached to messages).

    Example:
        kb = InlineKeyboard()
        kb.add_button("Click me", callback_data=b"click")
        kb.add_row()
        kb.add_button("Visit", url="https://telegram.org")

        await client.send_message(peer, "Hello", reply_markup=kb.build())
    """

    _rows: list[list[InlineButton]] = field(default_factory=list)
    _current_row: list[InlineButton] = field(default_factory=list)

    def add_button(
        self,
        text: str,
        *,
        callback_data: bytes | str | None = None,
        url: str | None = None,
        switch_inline_query: str | None = None,
        switch_inline_query_current_chat: str | None = None,
        web_app_url: str | None = None,
        copy_text: str | None = None,
    ) -> "InlineKeyboard":
        """Add a button to the current row."""
        data = callback_data.encode() if isinstance(callback_data, str) else callback_data
        self._current_row.append(
            InlineButton(
                text=text,
                callback_data=data,
                url=url,
                switch_inline_query=switch_inline_query,
                switch_inline_query_current_chat=switch_inline_query_current_chat,
                web_app_url=web_app_url,
                copy_text=copy_text,
            )
        )
        return self

    def add_row(self) -> "InlineKeyboard":
        """Finish current row and start a new one."""
        if self._current_row:
            self._rows.append(self._current_row)
            self._current_row = []
        return self

    def button(
        self,
        text: str,
        callback_data: bytes | str | None = None,
        url: str | None = None,
    ) -> "InlineKeyboard":
        """Shorthand for add_button with common options."""
        return self.add_button(text, callback_data=callback_data, url=url)

    def row(self) -> "InlineKeyboard":
        """Alias for add_row()."""
        return self.add_row()

    def build(self) -> ReplyInlineMarkup:
        """Build the inline keyboard markup."""
        # Finalize current row if not empty
        rows = self._rows.copy()
        if self._current_row:
            rows.append(self._current_row)

        tl_rows = [
            KeyboardButtonRow(buttons=[btn.to_tl() for btn in row]) for row in rows
        ]
        return ReplyInlineMarkup(rows=tl_rows)


# ========================== Reply Keyboard ==========================


@dataclass
class ReplyButton:
    """Helper class to create reply keyboard buttons."""

    text: str
    request_phone: bool = False
    request_location: bool = False

    def to_tl(self) -> Any:
        """Convert to TL object."""
        if self.request_phone:
            return KeyboardButtonRequestPhone(text=self.text)
        if self.request_location:
            return KeyboardButtonRequestGeoLocation(text=self.text)
        return KeyboardButton(text=self.text)


@dataclass
class ReplyKeyboard:
    """
    Builder for reply keyboards (custom keyboards replacing the default).

    Example:
        kb = ReplyKeyboard(resize=True)
        kb.add_button("Option 1")
        kb.add_button("Option 2")
        kb.add_row()
        kb.add_button("Share Phone", request_phone=True)

        await client.send_message(peer, "Choose:", reply_markup=kb.build())
    """

    resize: bool = True
    single_use: bool = False
    selective: bool = False
    persistent: bool = False
    placeholder: str | None = None

    _rows: list[list[ReplyButton]] = field(default_factory=list)
    _current_row: list[ReplyButton] = field(default_factory=list)

    def add_button(
        self,
        text: str,
        *,
        request_phone: bool = False,
        request_location: bool = False,
    ) -> "ReplyKeyboard":
        """Add a button to the current row."""
        self._current_row.append(
            ReplyButton(
                text=text,
                request_phone=request_phone,
                request_location=request_location,
            )
        )
        return self

    def add_row(self) -> "ReplyKeyboard":
        """Finish current row and start a new one."""
        if self._current_row:
            self._rows.append(self._current_row)
            self._current_row = []
        return self

    def button(self, text: str) -> "ReplyKeyboard":
        """Shorthand for add_button with just text."""
        return self.add_button(text)

    def row(self) -> "ReplyKeyboard":
        """Alias for add_row()."""
        return self.add_row()

    def build(self) -> ReplyKeyboardMarkup:
        """Build the reply keyboard markup."""
        rows = self._rows.copy()
        if self._current_row:
            rows.append(self._current_row)

        flags = 0
        if self.resize:
            flags |= 1
        if self.single_use:
            flags |= 2
        if self.selective:
            flags |= 4
        if self.placeholder is not None:
            flags |= 8
        if self.persistent:
            flags |= 16

        tl_rows = [
            KeyboardButtonRow(buttons=[btn.to_tl() for btn in row]) for row in rows
        ]
        return ReplyKeyboardMarkup(
            flags=flags,
            resize=self.resize if self.resize else None,
            single_use=self.single_use if self.single_use else None,
            selective=self.selective if self.selective else None,
            persistent=self.persistent if self.persistent else None,
            rows=tl_rows,
            placeholder=self.placeholder,
        )


# ========================== Keyboard Removal ==========================


def remove_keyboard(selective: bool = False) -> ReplyKeyboardHide:
    """
    Create a keyboard removal object to hide the reply keyboard.

    Args:
        selective: If True, only removes keyboard for mentioned users
    """
    flags = 4 if selective else 0
    return ReplyKeyboardHide(flags=flags, selective=selective if selective else None)


def force_reply(
    selective: bool = False, placeholder: str | None = None
) -> ReplyKeyboardForceReply:
    """
    Create a force reply object that shows reply interface to user.

    Args:
        selective: If True, only forces reply for mentioned users
        placeholder: Placeholder text for input field
    """
    flags = 0
    if selective:
        flags |= 4
    if placeholder is not None:
        flags |= 8
    return ReplyKeyboardForceReply(
        flags=flags,
        single_use=None,
        selective=selective if selective else None,
        placeholder=placeholder,
    )
