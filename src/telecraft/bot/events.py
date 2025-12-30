from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast


def _decode_text(v: object) -> str | None:
    if v is None:
        return None
    if isinstance(v, str):
        return v
    if isinstance(v, (bytes, bytearray)):
        return bytes(v).decode("utf-8", "replace")
    return str(v)


@dataclass(slots=True)
class MessageEvent:
    """
    Minimal message-like event for the bot framework.
    """

    client: Any
    raw: Any

    # best-effort identifiers
    chat_id: int | None = None
    user_id: int | None = None
    msg_id: int | None = None
    date: int | None = None
    text: str | None = None

    async def reply(self, text: str) -> Any:
        """
        Reply to the same basic chat if possible.

        For now:
        - if chat_id exists: reply to that chat
        - else: fallback to send-self
        """

        if self.chat_id is not None:
            return await self.client.send_message_chat(self.chat_id, text)
        return await self.client.send_message_self(text)

    @classmethod
    def from_update(cls, *, client: Any, update: Any) -> MessageEvent | None:
        name = getattr(update, "TL_NAME", None)

        if name == "updateShortChatMessage":
            return cls(
                client=client,
                raw=update,
                chat_id=int(cast(int, update.chat_id)),
                user_id=int(cast(int, update.from_id)),
                msg_id=int(cast(int, update.id)),
                date=int(cast(int, update.date)),
                text=_decode_text(getattr(update, "message", None)),
            )

        if name == "updateShortMessage":
            return cls(
                client=client,
                raw=update,
                chat_id=None,
                user_id=int(cast(int, update.user_id)),
                msg_id=int(cast(int, update.id)),
                date=int(cast(int, update.date)),
                text=_decode_text(getattr(update, "message", None)),
            )

        # Many other update types exist; we'll extend later.
        return None

