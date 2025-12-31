from __future__ import annotations

from telecraft.bot.events import MessageEvent


def test_event_command_parsing() -> None:
    e = MessageEvent(client=object(), raw=object(), text="/start 1 2 3")
    assert e.command == "start"
    assert e.command_args == "1 2 3"

    e2 = MessageEvent(client=object(), raw=object(), text="hi")
    assert e2.command is None
    assert e2.command_args is None


