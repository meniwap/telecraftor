from __future__ import annotations

from apps.streamingbot.markup import make_inline_menu, make_reply_keyboard, make_result_actions


def test_streamingbot_markup__reply_keyboard__has_expected_labels() -> None:
    markup = make_reply_keyboard()
    labels = [[button["text"] for button in row] for row in markup["keyboard"]]
    assert labels == [["בדיחות", "סיפור", "באטל"], ["תחזית", "עזרה", "עצור"]]


def test_streamingbot_markup__inline_menu__uses_expected_callback_values() -> None:
    markup = make_inline_menu()
    callback_data = {
        button["callback_data"]
        for row in markup["inline_keyboard"]
        for button in row
    }
    assert callback_data == {
        "mode:joke",
        "mode:story",
        "mode:fortune",
        "rerun:last",
        "reroll:last",
        "stop",
    }


def test_streamingbot_markup__result_actions__contain_expected_controls() -> None:
    markup = make_result_actions()
    callback_data = [
        button["callback_data"]
        for row in markup["inline_keyboard"]
        for button in row
    ]
    assert "rerun:last" in callback_data
    assert "reroll:last" in callback_data
    assert "menu" in callback_data
    assert "stop" in callback_data
