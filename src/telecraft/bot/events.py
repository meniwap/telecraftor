from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, cast

logger = logging.getLogger(__name__)


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
    channel_id: int | None = None
    user_id: int | None = None
    msg_id: int | None = None
    date: int | None = None
    text: str | None = None

    async def reply(self, text: str) -> Any:
        """
        Reply to the same basic chat if possible.

        Best-effort reply:
        - basic groups: send_message_chat(chat_id)
        - channels/supergroups: send_message_channel(channel_id) (requires access_hash primed)
        - private chats: send_message_user(user_id) (requires access_hash primed)
        - fallback: send_message_self()
        """

        if self.chat_id is not None:
            return await self.client.send_message_chat(self.chat_id, text)
        if self.channel_id is not None:
            try:
                return await self.client.send_message_channel(self.channel_id, text)
            except Exception as ex:  # noqa: BLE001
                logger.info("send_message_channel failed; falling back to self", exc_info=ex)
                return await self.client.send_message_self(text)
        if self.user_id is not None:
            try:
                return await self.client.send_message_user(self.user_id, text)
            except Exception as ex:  # noqa: BLE001
                logger.info("send_message_user failed; falling back to self", exc_info=ex)
                return await self.client.send_message_self(text)
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

        # Message objects (often arrive via getDifference.new_messages).
        if name in {"message", "messageService"}:
            peer = getattr(update, "peer_id", None)
            peer_name = getattr(peer, "TL_NAME", None)

            chat_id: int | None = None
            channel_id: int | None = None
            user_peer_id: int | None = None

            if peer_name == "peerChat":
                chat_id = int(cast(int, getattr(peer, "chat_id")))
            elif peer_name == "peerChannel":
                channel_id = int(cast(int, getattr(peer, "channel_id")))
            elif peer_name == "peerUser":
                user_peer_id = int(cast(int, getattr(peer, "user_id")))

            # Sender (best-effort): from_id may be absent or not a user.
            from_peer = getattr(update, "from_id", None)
            from_name = getattr(from_peer, "TL_NAME", None)
            sender_user_id: int | None = None
            if from_name == "peerUser":
                sender_user_id = int(cast(int, getattr(from_peer, "user_id")))

            return cls(
                client=client,
                raw=update,
                chat_id=chat_id,
                channel_id=channel_id,
                # Keep user_id as "sender user" when available.
                # For private chats, fall back to the peer user id.
                user_id=sender_user_id if sender_user_id is not None else user_peer_id,
                msg_id=int(cast(int, getattr(update, "id"))),
                date=int(cast(int, getattr(update, "date"))),
                text=_decode_text(getattr(update, "message", None)),
            )

        # Many other update types exist; we'll extend later.
        return None

