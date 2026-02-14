from __future__ import annotations

import pytest

from telecraft.client import Client


class _Raw:
    pass


@pytest.mark.unit
def test_messages_announcements_api__subclients__available() -> None:
    client = Client(raw=_Raw())
    assert hasattr(client.messages, "chat_theme")
    assert hasattr(client.messages, "suggested_posts")
    assert hasattr(client.messages, "fact_checks")
    assert hasattr(client.messages, "sponsored")
    assert hasattr(client.messages, "saved_tags")
    assert hasattr(client.messages, "attach_menu")
    assert hasattr(client.messages.inline, "prepared")
    assert hasattr(client.messages.web, "request_main")
