from __future__ import annotations

from typing import Any


def make_reply_keyboard() -> dict[str, Any]:
    return {
        "keyboard": [
            [{"text": "בדיחות"}, {"text": "סיפור"}, {"text": "באטל"}],
            [{"text": "תחזית"}, {"text": "עזרה"}, {"text": "עצור"}],
        ],
        "resize_keyboard": True,
        "is_persistent": True,
        "input_field_placeholder": "כתוב פקודה או בחר מצב",
    }


def make_inline_menu() -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {"text": "בדיחות", "callback_data": "mode:joke"},
                {"text": "סיפור", "callback_data": "mode:story"},
                {"text": "תחזית", "callback_data": "mode:fortune"},
            ],
            [
                {"text": "עוד כזה", "callback_data": "rerun:last"},
                {"text": "ערבב", "callback_data": "reroll:last"},
                {"text": "עצור", "callback_data": "stop"},
            ],
        ]
    }


def make_result_actions() -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {"text": "עוד כזה", "callback_data": "rerun:last"},
                {"text": "ערבב", "callback_data": "reroll:last"},
                {"text": "תפריט", "callback_data": "menu"},
            ],
            [
                {"text": "בדיחות", "callback_data": "mode:joke"},
                {"text": "סיפור", "callback_data": "mode:story"},
                {"text": "תחזית", "callback_data": "mode:fortune"},
            ],
            [{"text": "עצור", "callback_data": "stop"}],
        ]
    }
