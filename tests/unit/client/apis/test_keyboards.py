"""
Tests for keyboard builders.
"""

from telecraft.client.keyboards import (
    InlineButton,
    InlineKeyboard,
    ReplyButton,
    ReplyKeyboard,
    force_reply,
    remove_keyboard,
)
from telecraft.tl.generated.types import (
    KeyboardButton,
    KeyboardButtonCallback,
    KeyboardButtonRequestGeoLocation,
    KeyboardButtonRequestPhone,
    KeyboardButtonSwitchInline,
    KeyboardButtonUrl,
    KeyboardButtonWebView,
    ReplyInlineMarkup,
    ReplyKeyboardForceReply,
    ReplyKeyboardHide,
    ReplyKeyboardMarkup,
)


class TestInlineButton:
    def test_callback_button(self) -> None:
        btn = InlineButton(text="Click", callback_data=b"test")
        tl = btn.to_tl()
        assert isinstance(tl, KeyboardButtonCallback)
        assert tl.text == "Click"
        assert tl.data == b"test"

    def test_url_button(self) -> None:
        btn = InlineButton(text="Visit", url="https://example.com")
        tl = btn.to_tl()
        assert isinstance(tl, KeyboardButtonUrl)
        assert tl.text == "Visit"
        assert tl.url == "https://example.com"

    def test_switch_inline_button(self) -> None:
        btn = InlineButton(text="Search", switch_inline_query="query")
        tl = btn.to_tl()
        assert isinstance(tl, KeyboardButtonSwitchInline)
        assert tl.text == "Search"
        assert tl.query == "query"

    def test_web_app_button(self) -> None:
        btn = InlineButton(text="Open App", web_app_url="https://app.example.com")
        tl = btn.to_tl()
        assert isinstance(tl, KeyboardButtonWebView)
        assert tl.text == "Open App"
        assert tl.url == "https://app.example.com"


class TestInlineKeyboard:
    def test_build_single_row(self) -> None:
        kb = InlineKeyboard()
        kb.add_button("A", callback_data=b"a")
        kb.add_button("B", callback_data=b"b")
        markup = kb.build()

        assert isinstance(markup, ReplyInlineMarkup)
        assert len(markup.rows) == 1
        assert len(markup.rows[0].buttons) == 2

    def test_build_multiple_rows(self) -> None:
        kb = InlineKeyboard()
        kb.add_button("A", callback_data=b"a")
        kb.add_row()
        kb.add_button("B", callback_data=b"b")
        markup = kb.build()

        assert len(markup.rows) == 2
        assert len(markup.rows[0].buttons) == 1
        assert len(markup.rows[1].buttons) == 1

    def test_fluent_api(self) -> None:
        kb = (
            InlineKeyboard()
            .button("A", callback_data="a")
            .button("B", url="https://t.me")
            .row()
            .button("C", callback_data="c")
        )
        markup = kb.build()

        assert len(markup.rows) == 2
        assert len(markup.rows[0].buttons) == 2
        assert len(markup.rows[1].buttons) == 1

    def test_string_callback_data_encoded(self) -> None:
        kb = InlineKeyboard()
        kb.add_button("Test", callback_data="hello")
        markup = kb.build()

        btn = markup.rows[0].buttons[0]
        assert btn.data == b"hello"


class TestReplyButton:
    def test_text_button(self) -> None:
        btn = ReplyButton(text="Hello")
        tl = btn.to_tl()
        assert isinstance(tl, KeyboardButton)
        assert tl.text == "Hello"

    def test_phone_button(self) -> None:
        btn = ReplyButton(text="Share Phone", request_phone=True)
        tl = btn.to_tl()
        assert isinstance(tl, KeyboardButtonRequestPhone)
        assert tl.text == "Share Phone"

    def test_location_button(self) -> None:
        btn = ReplyButton(text="Share Location", request_location=True)
        tl = btn.to_tl()
        assert isinstance(tl, KeyboardButtonRequestGeoLocation)
        assert tl.text == "Share Location"


class TestReplyKeyboard:
    def test_build_basic(self) -> None:
        kb = ReplyKeyboard()
        kb.add_button("Option 1")
        kb.add_button("Option 2")
        markup = kb.build()

        assert isinstance(markup, ReplyKeyboardMarkup)
        assert len(markup.rows) == 1
        assert len(markup.rows[0].buttons) == 2

    def test_resize_flag(self) -> None:
        kb = ReplyKeyboard(resize=True)
        kb.add_button("Test")
        markup = kb.build()

        assert markup.resize is True

    def test_single_use_flag(self) -> None:
        kb = ReplyKeyboard(single_use=True)
        kb.add_button("Test")
        markup = kb.build()

        assert markup.single_use is True

    def test_placeholder(self) -> None:
        kb = ReplyKeyboard(placeholder="Type here...")
        kb.add_button("Test")
        markup = kb.build()

        assert markup.placeholder == "Type here..."

    def test_request_phone_button(self) -> None:
        kb = ReplyKeyboard()
        kb.add_button("Share Phone", request_phone=True)
        markup = kb.build()

        assert isinstance(markup.rows[0].buttons[0], KeyboardButtonRequestPhone)


class TestRemoveKeyboard:
    def test_basic_removal(self) -> None:
        markup = remove_keyboard()
        assert isinstance(markup, ReplyKeyboardHide)

    def test_selective_removal(self) -> None:
        markup = remove_keyboard(selective=True)
        assert isinstance(markup, ReplyKeyboardHide)
        assert markup.selective is True


class TestForceReply:
    def test_basic_force_reply(self) -> None:
        markup = force_reply()
        assert isinstance(markup, ReplyKeyboardForceReply)

    def test_with_placeholder(self) -> None:
        markup = force_reply(placeholder="Reply here...")
        assert isinstance(markup, ReplyKeyboardForceReply)
        assert markup.placeholder == "Reply here..."

    def test_selective(self) -> None:
        markup = force_reply(selective=True)
        assert isinstance(markup, ReplyKeyboardForceReply)
        assert markup.selective is True
