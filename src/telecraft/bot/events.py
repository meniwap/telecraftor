from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, cast

logger = logging.getLogger(__name__)

def _peer_type_and_id(peer: object) -> tuple[str | None, int | None]:
    name = getattr(peer, "TL_NAME", None)
    if name == "peerUser":
        v = getattr(peer, "user_id", None)
        return ("user", int(v)) if isinstance(v, int) else (None, None)
    if name == "peerChat":
        v = getattr(peer, "chat_id", None)
        return ("chat", int(v)) if isinstance(v, int) else (None, None)
    if name == "peerChannel":
        v = getattr(peer, "channel_id", None)
        return ("channel", int(v)) if isinstance(v, int) else (None, None)
    return None, None

def _flag_is_set(flags: object, bit: int) -> bool:
    try:
        return (int(cast(int, flags)) & (1 << bit)) != 0
    except Exception:  # noqa: BLE001
        return False


def _decode_text(v: object) -> str | None:
    if v is None:
        return None
    if isinstance(v, str):
        return v
    if isinstance(v, (bytes, bytearray)):
        return bytes(v).decode("utf-8", "replace")
    return str(v)

def _parse_command(text: str) -> tuple[str | None, str | None]:
    """
    Minimal command parsing:
      "/start arg1 arg2" -> ("start", "arg1 arg2")
      "hi" -> (None, None)
    """
    t = text.strip()
    if not t.startswith("/"):
        return None, None
    body = t[1:]
    if not body:
        return None, None
    head, _, rest = body.partition(" ")
    # handle "/cmd@botname"
    name = head.split("@", 1)[0].strip()
    if not name:
        return None, None
    args = rest.strip() if rest.strip() else None
    return name, args


def _fill_peer_fields(e: MessageEvent) -> MessageEvent:
    """
    Backfill peer_type/peer_id from legacy fields when missing.
    """
    if e.peer_type is not None and e.peer_id is not None:
        return e
    if e.chat_id is not None:
        e.peer_type = "chat"
        e.peer_id = int(e.chat_id)
        return e
    if e.channel_id is not None:
        e.peer_type = "channel"
        e.peer_id = int(e.channel_id)
        return e
    if e.user_id is not None:
        e.peer_type = "user"
        e.peer_id = int(e.user_id)
        return e
    return e


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
    # Backward-compat: historically used as "sender user id" (if known), else peer user id.
    user_id: int | None = None
    # Preferred: explicit sender id (user). May be None (e.g. outgoing short updates).
    sender_id: int | None = None
    # Preferred: explicit peer info.
    peer_type: str | None = None  # "user" | "chat" | "channel"
    peer_id: int | None = None
    msg_id: int | None = None
    date: int | None = None
    text: str | None = None
    outgoing: bool = False
    kind: str = "new"  # "new" | "edit"

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

    @property
    def has_media(self) -> bool:
        media = getattr(self.raw, "media", None)
        return media is not None

    @property
    def reply_to_msg_id(self) -> int | None:
        rh = getattr(self.raw, "reply_to", None)
        if rh is None:
            return None
        v = getattr(rh, "reply_to_msg_id", None)
        return int(v) if isinstance(v, int) else None

    @property
    def is_private(self) -> bool:
        return self.peer_type == "user" and self.peer_id is not None

    @property
    def is_group(self) -> bool:
        return self.peer_type == "chat" and self.peer_id is not None

    @property
    def is_channel(self) -> bool:
        return self.peer_type == "channel" and self.peer_id is not None

    @property
    def command(self) -> str | None:
        if not self.text:
            return None
        name, _args = _parse_command(self.text)
        return name

    @property
    def command_args(self) -> str | None:
        if not self.text:
            return None
        _name, args = _parse_command(self.text)
        return args

    @classmethod
    def from_update(cls, *, client: Any, update: Any) -> MessageEvent | None:
        name = getattr(update, "TL_NAME", None)

        # Common update wrappers that carry a Message/MessageService in `.message`.
        if name in {
            "updateNewMessage",
            "updateNewChannelMessage",
            "updateEditMessage",
            "updateEditChannelMessage",
        }:
            kind = "edit" if name in {"updateEditMessage", "updateEditChannelMessage"} else "new"
            inner = getattr(update, "message", None)
            if inner is not None:
                e = cls.from_update(client=client, update=inner)
                if e is not None:
                    e.kind = kind
                return e

        if name == "updateShortChatMessage":
            outgoing = _flag_is_set(getattr(update, "flags", 0), 1)
            chat_id_val = int(cast(int, update.chat_id))
            sender_id_val = int(cast(int, update.from_id))
            return _fill_peer_fields(
                cls(
                    client=client,
                    raw=update,
                    chat_id=chat_id_val,
                    user_id=sender_id_val,
                    sender_id=sender_id_val,
                    peer_type="chat",
                    peer_id=chat_id_val,
                    msg_id=int(cast(int, update.id)),
                    date=int(cast(int, update.date)),
                    text=_decode_text(getattr(update, "message", None)),
                    outgoing=outgoing,
                    kind="new",
                )
            )

        if name == "updateShortMessage":
            outgoing = _flag_is_set(getattr(update, "flags", 0), 1)
            peer_user_id = int(cast(int, update.user_id))
            # NOTE: for outgoing short messages, user_id may represent the other party,
            # but we don't have "self id" here. Keep sender_id=None in that case.
            sender_id_val2: int | None = peer_user_id if not outgoing else None
            return _fill_peer_fields(
                cls(
                    client=client,
                    raw=update,
                    chat_id=None,
                    user_id=sender_id_val2 if sender_id_val2 is not None else peer_user_id,
                    sender_id=sender_id_val2,
                    peer_type="user",
                    peer_id=peer_user_id,
                    msg_id=int(cast(int, update.id)),
                    date=int(cast(int, update.date)),
                    text=_decode_text(getattr(update, "message", None)),
                    outgoing=outgoing,
                    kind="new",
                )
            )

        # Message objects (often arrive via getDifference.new_messages).
        if name in {"message", "messageService"}:
            outgoing = _flag_is_set(getattr(update, "flags", 0), 1)
            peer = getattr(update, "peer_id", None)
            peer_name = getattr(peer, "TL_NAME", None)

            chat_id_val2: int | None = None
            channel_id_val2: int | None = None
            user_peer_id: int | None = None
            peer_type: str | None = None
            peer_id: int | None = None

            if peer_name == "peerChat":
                chat_id_val2 = int(cast(int, getattr(peer, "chat_id")))
                peer_type, peer_id = "chat", chat_id_val2
            elif peer_name == "peerChannel":
                channel_id_val2 = int(cast(int, getattr(peer, "channel_id")))
                peer_type, peer_id = "channel", channel_id_val2
            elif peer_name == "peerUser":
                user_peer_id = int(cast(int, getattr(peer, "user_id")))
                peer_type, peer_id = "user", user_peer_id

            # Sender (best-effort): from_id may be absent or not a user.
            from_peer = getattr(update, "from_id", None)
            from_name = getattr(from_peer, "TL_NAME", None)
            sender_user_id: int | None = None
            if from_name == "peerUser":
                sender_user_id = int(cast(int, getattr(from_peer, "user_id")))

            compat_user_id = sender_user_id if sender_user_id is not None else user_peer_id
            return _fill_peer_fields(
                cls(
                    client=client,
                    raw=update,
                    chat_id=chat_id_val2,
                    channel_id=channel_id_val2,
                    # Keep user_id as "sender user" when available.
                    # For private chats, fall back to the peer user id.
                    user_id=compat_user_id,
                    sender_id=sender_user_id,
                    peer_type=peer_type,
                    peer_id=peer_id,
                    msg_id=int(cast(int, getattr(update, "id"))),
                    date=int(cast(int, getattr(update, "date"))),
                    text=_decode_text(getattr(update, "message", None)),
                    outgoing=outgoing,
                    kind="new",
                )
            )

        # Many other update types exist; we'll extend later.
        return None


@dataclass(slots=True)
class ReactionEvent:
    client: Any
    raw: Any
    peer_type: str | None
    peer_id: int | None
    msg_id: int
    reactions: Any

    @classmethod
    def from_update(cls, *, client: Any, update: Any) -> ReactionEvent | None:
        name = getattr(update, "TL_NAME", None)

        # Primary reaction update type.
        if name == "updateMessageReactions":
            peer = getattr(update, "peer", None)
            peer_type, peer_id = _peer_type_and_id(peer)
            msg_id = getattr(update, "msg_id", None)
            if not isinstance(msg_id, int):
                return None
            return cls(
                client=client,
                raw=update,
                peer_type=peer_type,
                peer_id=peer_id,
                msg_id=int(msg_id),
                reactions=getattr(update, "reactions", None),
            )

        # Some clients receive reactions as message edits (message.reactions changes).
        if name in {"updateEditMessage", "updateEditChannelMessage"}:
            inner = getattr(update, "message", None)
            if inner is None:
                return None
            reactions = getattr(inner, "reactions", None)
            if reactions is None:
                return None
            peer = getattr(inner, "peer_id", None)
            peer_type, peer_id = _peer_type_and_id(peer)
            msg_id = getattr(inner, "id", None)
            if not isinstance(msg_id, int):
                return None
            return cls(
                client=client,
                raw=update,
                peer_type=peer_type,
                peer_id=peer_id,
                msg_id=int(msg_id),
                reactions=reactions,
            )

        return None


@dataclass(slots=True)
class DeletedMessagesEvent:
    client: Any
    raw: Any
    peer_type: str | None
    peer_id: int | None
    msg_ids: list[int]

    @classmethod
    def from_update(cls, *, client: Any, update: Any) -> DeletedMessagesEvent | None:
        name = getattr(update, "TL_NAME", None)
        if name == "updateDeleteChannelMessages":
            cid = getattr(update, "channel_id", None)
            msgs = getattr(update, "messages", None)
            if not isinstance(cid, int) or not isinstance(msgs, list):
                return None
            ids = [int(x) for x in msgs if isinstance(x, int)]
            return cls(
                client=client,
                raw=update,
                peer_type="channel",
                peer_id=int(cid),
                msg_ids=ids,
            )
        if name == "updateDeleteMessages":
            msgs = getattr(update, "messages", None)
            if not isinstance(msgs, list):
                return None
            ids = [int(x) for x in msgs if isinstance(x, int)]
            # No peer info in this update type.
            return cls(client=client, raw=update, peer_type=None, peer_id=None, msg_ids=ids)
        return None


BotEvent = MessageEvent | ReactionEvent | DeletedMessagesEvent


def parse_events(*, client: Any, update: Any) -> list[BotEvent]:
    """
    Convert a raw TL update/message object into 0..N bot events.
    """
    out: list[BotEvent] = []
    m = MessageEvent.from_update(client=client, update=update)
    if m is not None:
        out.append(m)

    r = ReactionEvent.from_update(client=client, update=update)
    if r is not None:
        out.append(r)

    d = DeletedMessagesEvent.from_update(client=client, update=update)
    if d is not None:
        out.append(d)

    return out

