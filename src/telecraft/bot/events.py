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
    # Set by Dispatcher according to backlog policy / throttling decisions.
    is_backlog: bool = False
    allow_reply: bool = True

    async def reply(self, text: str) -> Any:
        """
        Reply to the same basic chat if possible.

        Best-effort reply:
        - basic groups: send_message_chat(chat_id)
        - channels/supergroups: send_message_channel(channel_id) (requires access_hash primed)
        - private chats: send_message_user(user_id) (requires access_hash primed)
        - fallback: send_message_self()
        """

        if not self.allow_reply:
            logger.info(
                "Suppressed reply (allow_reply=False) peer=%s:%s msg_id=%s",
                self.peer_type,
                self.peer_id,
                self.msg_id,
            )
            return None

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
    def edit_date(self) -> int | None:
        v = getattr(self.raw, "edit_date", None)
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
class ChatActionEvent:
    """
    Chat/service action event derived from a MessageService (Telegram service message).

    Examples:
    - join/leave (add/delete user)
    - pin message
    - title/photo changes
    """

    client: Any
    raw: Any  # messageService object

    peer_type: str | None
    peer_id: int | None
    msg_id: int | None
    date: int | None
    sender_id: int | None
    outgoing: bool = False

    # Canonical kind for convenient filters.
    kind: str = "other"  # "join" | "leave" | "pin" | "title" | "photo" | "other"
    action_name: str | None = None  # TL_NAME of the action, if available

    # Best-effort details (optional; not exhaustive)
    added_user_ids: list[int] | None = None
    removed_user_id: int | None = None
    pinned_msg_id: int | None = None
    new_title: str | None = None
    inviter_id: int | None = None
    photo: Any | None = None
    migrated_to_channel_id: int | None = None
    migrated_from_chat_id: int | None = None
    migrated_from_title: str | None = None

    # Set by Dispatcher according to backlog policy / throttling decisions.
    is_backlog: bool = False
    allow_reply: bool = True

    @property
    def is_private(self) -> bool:
        return self.peer_type == "user" and self.peer_id is not None

    @property
    def is_group(self) -> bool:
        return self.peer_type == "chat" and self.peer_id is not None

    @property
    def is_channel(self) -> bool:
        return self.peer_type == "channel" and self.peer_id is not None

    async def reply(self, text: str) -> Any:
        """
        Best-effort reply to the same peer (like MessageEvent.reply, but using peer_type/id).
        """
        if not self.allow_reply:
            logger.info(
                "Suppressed reply (allow_reply=False) peer=%s:%s action=%s msg_id=%s",
                self.peer_type,
                self.peer_id,
                self.action_name,
                self.msg_id,
            )
            return None

        if self.peer_type == "chat" and self.peer_id is not None:
            return await self.client.send_message_chat(int(self.peer_id), text)
        if self.peer_type == "channel" and self.peer_id is not None:
            try:
                return await self.client.send_message_channel(int(self.peer_id), text)
            except Exception as ex:  # noqa: BLE001
                logger.info("send_message_channel failed; falling back to self", exc_info=ex)
                return await self.client.send_message_self(text)
        if self.peer_type == "user" and self.peer_id is not None:
            try:
                return await self.client.send_message_user(int(self.peer_id), text)
            except Exception as ex:  # noqa: BLE001
                logger.info("send_message_user failed; falling back to self", exc_info=ex)
                return await self.client.send_message_self(text)
        return await self.client.send_message_self(text)

    @classmethod
    def from_update(cls, *, client: Any, update: Any) -> ChatActionEvent | None:
        """
        Extract a ChatActionEvent from:
        - updateNewMessage/updateNewChannelMessage/updateEdit... wrappers that carry `.message`
        - raw messageService objects
        """
        name = getattr(update, "TL_NAME", None)

        # Common update wrappers that carry a Message/MessageService in `.message`.
        if name in {
            "updateNewMessage",
            "updateNewChannelMessage",
            "updateEditMessage",
            "updateEditChannelMessage",
        }:
            inner = getattr(update, "message", None)
            if inner is None:
                return None
            return cls.from_update(client=client, update=inner)

        if name != "messageService":
            return None

        action = getattr(update, "action", None)
        action_name = getattr(action, "TL_NAME", None)
        if action is None or not action_name:
            return None

        outgoing = _flag_is_set(getattr(update, "flags", 0), 1)

        peer = getattr(update, "peer_id", None)
        peer_type, peer_id = _peer_type_and_id(peer)

        # Sender (best-effort): from_id may be absent or not a user.
        from_peer = getattr(update, "from_id", None)
        from_name = getattr(from_peer, "TL_NAME", None)
        sender_user_id: int | None = None
        if from_name == "peerUser":
            v = getattr(from_peer, "user_id", None)
            sender_user_id = int(v) if isinstance(v, int) else None

        kind = "other"
        added_user_ids: list[int] | None = None
        removed_user_id: int | None = None
        pinned_msg_id: int | None = None
        new_title: str | None = None
        inviter_id: int | None = None
        photo: Any | None = None
        migrated_to_channel_id: int | None = None
        migrated_from_chat_id: int | None = None
        migrated_from_title: str | None = None

        if action_name in {
            "messageActionChatAddUser",
            "messageActionChatJoinedByLink",
            "messageActionChatJoinedByRequest",
        }:
            kind = "join"
            if action_name == "messageActionChatAddUser":
                users = getattr(action, "users", None)
                if isinstance(users, list):
                    added_user_ids = [int(x) for x in users if isinstance(x, int)]
            if action_name == "messageActionChatJoinedByLink":
                inv = getattr(action, "inviter_id", None)
                inviter_id = int(inv) if isinstance(inv, int) else None
        elif action_name == "messageActionChatDeleteUser":
            kind = "leave"
            uid = getattr(action, "user_id", None)
            removed_user_id = int(uid) if isinstance(uid, int) else None
        elif action_name == "messageActionPinMessage":
            kind = "pin"
            # messageActionPinMessage has no fields; pinned msg id is usually in reply header.
            rh = getattr(update, "reply_to", None)
            mid = getattr(rh, "reply_to_msg_id", None) if rh is not None else None
            pinned_msg_id = int(mid) if isinstance(mid, int) else None
        elif action_name == "messageActionChatEditTitle":
            kind = "title"
            title = getattr(action, "title", None)
            new_title = _decode_text(title)
        elif action_name == "messageActionChatEditPhoto":
            kind = "photo"
            photo = getattr(action, "photo", None)
        elif action_name == "messageActionChatDeletePhoto":
            kind = "photo"
        elif action_name == "messageActionChatMigrateTo":
            kind = "migrate_to"
            cid = getattr(action, "channel_id", None)
            migrated_to_channel_id = int(cid) if isinstance(cid, int) else None
        elif action_name == "messageActionChannelMigrateFrom":
            kind = "migrate_from"
            cid2 = getattr(action, "chat_id", None)
            migrated_from_chat_id = int(cid2) if isinstance(cid2, int) else None
            migrated_from_title = _decode_text(getattr(action, "title", None))
        elif action_name == "messageActionChannelCreate":
            kind = "create"
            new_title = _decode_text(getattr(action, "title", None))

        mid2 = getattr(update, "id", None)
        date2 = getattr(update, "date", None)
        msg_id = int(mid2) if isinstance(mid2, int) else None
        date = int(date2) if isinstance(date2, int) else None

        return cls(
            client=client,
            raw=update,
            peer_type=peer_type,
            peer_id=peer_id,
            msg_id=msg_id,
            date=date,
            sender_id=sender_user_id,
            outgoing=outgoing,
            kind=kind,
            action_name=str(action_name) if action_name is not None else None,
            added_user_ids=added_user_ids,
            removed_user_id=removed_user_id,
            pinned_msg_id=pinned_msg_id,
            new_title=new_title,
            inviter_id=inviter_id,
            photo=photo,
            migrated_to_channel_id=migrated_to_channel_id,
            migrated_from_chat_id=migrated_from_chat_id,
            migrated_from_title=migrated_from_title,
        )


def _participant_role(p: object | None) -> str | None:
    """
    Collapse ChatParticipant/ChannelParticipant variants into a small role set.
    """
    if p is None:
        return None
    name = getattr(p, "TL_NAME", None)
    if not isinstance(name, str):
        return "other"
    if "Creator" in name or name.endswith("Creator"):
        return "creator"
    if "Admin" in name or name.endswith("Admin"):
        return "admin"
    if "Banned" in name or name.endswith("Banned"):
        return "banned"
    if "Left" in name or name.endswith("Left"):
        return "left"
    if name in {"chatParticipant", "channelParticipant", "channelParticipantSelf"}:
        return "member"
    return "other"


def _compute_member_kind(
    *,
    prev_participant: object | None,
    new_participant: object | None,
    actor_id: int | None,
    user_id: int | None,
) -> str:
    """
    Compute a stable kind from prev/new participant objects.
    Values are best-effort and intentionally coarse.
    """
    prev_role = _participant_role(prev_participant)
    new_role = _participant_role(new_participant)

    # Special-case channelParticipantBanned(left=true) -> treat as leave.
    if getattr(new_participant, "TL_NAME", None) == "channelParticipantBanned":
        left_flag = getattr(new_participant, "left", None)
        if left_flag is True:
            return "leave"
        return "ban"
    if getattr(new_participant, "TL_NAME", None) == "channelParticipantLeft":
        return "leave"

    if prev_participant is None and new_participant is not None:
        # Join/invite.
        if actor_id is not None and user_id is not None and actor_id != user_id:
            return "invite"
        return "join"

    if new_participant is None and prev_participant is not None:
        # Leave/kick.
        if actor_id is not None and user_id is not None and actor_id != user_id:
            return "kick"
        return "leave"

    if prev_role != new_role and prev_role is not None and new_role is not None:
        if new_role in {"admin", "creator"} and prev_role == "member":
            return "promote"
        if prev_role in {"admin", "creator"} and new_role == "member":
            return "demote"
        if new_role == "banned":
            return "ban"
        return "role_change"

    return "update"


@dataclass(slots=True)
class MemberUpdateEvent:
    """
    Participant/admin/ban updates that are NOT based on service messages.
    Typically arrives as updateChatParticipant/updateChannelParticipant.
    """

    client: Any
    raw: Any

    peer_type: str | None  # "chat" | "channel"
    peer_id: int | None

    date: int | None
    actor_id: int | None
    user_id: int | None

    prev_participant: Any | None = None
    new_participant: Any | None = None
    invite: Any | None = None
    qts: int | None = None
    via_chatlist: bool = False

    kind: str = "update"  # join/leave/invite/kick/promote/demote/ban/...

    # Set by Dispatcher according to backlog policy / throttling decisions.
    is_backlog: bool = False
    allow_reply: bool = True

    @property
    def is_group(self) -> bool:
        return self.peer_type == "chat" and self.peer_id is not None

    @property
    def is_channel(self) -> bool:
        return self.peer_type == "channel" and self.peer_id is not None

    @classmethod
    def from_update(cls, *, client: Any, update: Any) -> MemberUpdateEvent | None:
        name = getattr(update, "TL_NAME", None)
        if name not in {
            "updateChatParticipant",
            "updateChannelParticipant",
            "updateChatParticipantAdd",
            "updateChatParticipantDelete",
            "updateChatParticipantAdmin",
        }:
            return None

        if name in {
            "updateChatParticipant",
            "updateChatParticipantAdd",
            "updateChatParticipantDelete",
            "updateChatParticipantAdmin",
        }:
            chat_id = getattr(update, "chat_id", None)
            peer_type = "chat"
            peer_id = int(chat_id) if isinstance(chat_id, int) else None
        else:
            channel_id = getattr(update, "channel_id", None)
            peer_type = "channel"
            peer_id = int(channel_id) if isinstance(channel_id, int) else None

        # Legacy/basic-chat updates (older forms).
        if name == "updateChatParticipantAdd":
            date = getattr(update, "date", None)
            user = getattr(update, "user_id", None)
            inviter = getattr(update, "inviter_id", None)
            actor_id = int(inviter) if isinstance(inviter, int) else None
            user_id = int(user) if isinstance(user, int) else None
            date_i = int(date) if isinstance(date, int) else None
            kind = (
                "invite"
                if (actor_id is not None and user_id is not None and actor_id != user_id)
                else "join"
            )
            return cls(
                client=client,
                raw=update,
                peer_type=peer_type,
                peer_id=peer_id,
                date=date_i,
                actor_id=actor_id,
                user_id=user_id,
                prev_participant=None,
                new_participant=None,
                invite=None,
                qts=None,
                via_chatlist=False,
                kind=kind,
            )

        if name == "updateChatParticipantDelete":
            user = getattr(update, "user_id", None)
            user_id = int(user) if isinstance(user, int) else None
            # No date/actor in this legacy update type.
            return cls(
                client=client,
                raw=update,
                peer_type=peer_type,
                peer_id=peer_id,
                date=None,
                actor_id=None,
                user_id=user_id,
                prev_participant=None,
                new_participant=None,
                invite=None,
                qts=None,
                via_chatlist=False,
                kind="leave",
            )

        if name == "updateChatParticipantAdmin":
            user = getattr(update, "user_id", None)
            is_admin = getattr(update, "is_admin", None)
            user_id = int(user) if isinstance(user, int) else None
            kind = "promote" if is_admin is True else "demote"
            return cls(
                client=client,
                raw=update,
                peer_type=peer_type,
                peer_id=peer_id,
                date=None,
                actor_id=None,
                user_id=user_id,
                prev_participant=None,
                new_participant=None,
                invite=None,
                qts=None,
                via_chatlist=False,
                kind=kind,
            )

        # Modern updates.
        date = getattr(update, "date", None)
        actor = getattr(update, "actor_id", None)
        user = getattr(update, "user_id", None)
        prev_p = getattr(update, "prev_participant", None)
        new_p = getattr(update, "new_participant", None)
        invite = getattr(update, "invite", None)
        qts = getattr(update, "qts", None)
        via_chatlist = bool(getattr(update, "via_chatlist", False))

        actor_id = int(actor) if isinstance(actor, int) else None
        user_id = int(user) if isinstance(user, int) else None
        date_i = int(date) if isinstance(date, int) else None
        qts_i = int(qts) if isinstance(qts, int) else None

        kind = _compute_member_kind(
            prev_participant=prev_p,
            new_participant=new_p,
            actor_id=actor_id,
            user_id=user_id,
        )

        return cls(
            client=client,
            raw=update,
            peer_type=peer_type,
            peer_id=peer_id,
            date=date_i,
            actor_id=actor_id,
            user_id=user_id,
            prev_participant=prev_p,
            new_participant=new_p,
            invite=invite,
            qts=qts_i,
            via_chatlist=via_chatlist,
            kind=kind,
        )


@dataclass(slots=True)
class ReactionEvent:
    client: Any
    raw: Any
    peer_type: str | None
    peer_id: int | None
    msg_id: int
    reactions: Any
    # Set by Dispatcher according to backlog policy / throttling decisions.
    is_backlog: bool = False

    @staticmethod
    def _reaction_key(reaction: object) -> str | None:
        """
        Convert a TL Reaction into a stable key:
        - reactionEmoji -> the emoji string (e.g. "❤️")
        - reactionCustomEmoji -> "custom:<document_id>"
        - reactionPaid -> "paid"
        """
        name = getattr(reaction, "TL_NAME", None)
        if name == "reactionEmoji":
            v = getattr(reaction, "emoticon", None)
            # TL "string" is decoded as bytes by our codec; decode best-effort for emoji keys.
            if isinstance(v, bytes):
                try:
                    return v.decode("utf-8")
                except Exception:
                    return None
            return str(v) if isinstance(v, str) else None
        if name == "reactionCustomEmoji":
            v2 = getattr(reaction, "document_id", None)
            return f"custom:{int(v2)}" if isinstance(v2, int) else None
        if name == "reactionPaid":
            return "paid"
        if name == "reactionEmpty":
            return None
        return str(name) if isinstance(name, str) else None

    @property
    def counts(self) -> dict[str, int]:
        """
        Best-effort reaction counts, keyed by emoji or "custom:<id>".
        """
        out: dict[str, int] = {}
        mr = self.reactions
        # messageReactions.results: Vector<ReactionCount>
        results = getattr(mr, "results", None)
        if not isinstance(results, list):
            return out
        for rc in results:
            r = getattr(rc, "reaction", None)
            key = self._reaction_key(r)
            if not key:
                continue
            c = getattr(rc, "count", None)
            if not isinstance(c, int):
                continue
            out[key] = int(c)
        return out

    @property
    def total_count(self) -> int:
        return sum(self.counts.values())

    @property
    def my_reactions(self) -> list[str]:
        """
        Best-effort list of reactions that are "mine".

        Telegram can represent "my" reactions in (at least) two ways:
        - messageReactions.recent_reactions: MessagePeerReaction items with `my=true`
        - messageReactions.results: ReactionCount items with `chosen_order` set (after sendReaction)
        """
        mr = self.reactions

        # Preferred: recent_reactions with explicit my=true.
        out: list[str] = []
        recent = getattr(mr, "recent_reactions", None)
        if isinstance(recent, list):
            for pr in recent:
                if getattr(pr, "my", False) is not True:
                    continue
                key = self._reaction_key(getattr(pr, "reaction", None))
                if key:
                    out.append(key)
            if out:
                return out

        # Fallback: chosen_order on ReactionCount, which is set for user's reactions.
        results = getattr(mr, "results", None)
        if not isinstance(results, list):
            return []
        chosen: list[tuple[int, str]] = []
        for rc in results:
            co = getattr(rc, "chosen_order", None)
            if not isinstance(co, int):
                continue
            key = self._reaction_key(getattr(rc, "reaction", None))
            if key:
                chosen.append((int(co), key))
        chosen.sort(key=lambda x: x[0])
        return [k for _co, k in chosen]

    def has(self, reaction_key: str) -> bool:
        return reaction_key in self.counts

    def count(self, reaction_key: str) -> int:
        return int(self.counts.get(reaction_key, 0))

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
    # Set by Dispatcher according to backlog policy / throttling decisions.
    is_backlog: bool = False

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


BotEvent = MessageEvent | ChatActionEvent | MemberUpdateEvent | ReactionEvent | DeletedMessagesEvent


def parse_events(*, client: Any, update: Any) -> list[BotEvent]:
    """
    Convert a raw TL update/message object into 0..N bot events.
    """
    out: list[BotEvent] = []
    a = ChatActionEvent.from_update(client=client, update=update)
    mu = MemberUpdateEvent.from_update(client=client, update=update)
    # Prefer ReactionEvent over MessageEvent(kind="edit") when Telegram represents reaction
    # changes as updateEditMessage/updateEditChannelMessage.
    r = ReactionEvent.from_update(client=client, update=update)
    m = MessageEvent.from_update(client=client, update=update)
    if mu is not None:
        out.append(mu)
    if a is not None:
        out.append(a)
    elif m is not None:
        if r is not None and getattr(update, "TL_NAME", None) in {
            "updateEditMessage",
            "updateEditChannelMessage",
        }:
            # If we can emit a ReactionEvent from an edit-wrapper, treat it as a reaction update
            # and do not also emit an "edit" message event. This avoids double-triggering.
            #
            # Note: this can hide "real" edits on messages that also have reactions, but keeps
            # the common case (reaction updates) intuitive. We can add a more granular model later.
            pass
        else:
            out.append(m)
    if r is not None:
        out.append(r)

    d = DeletedMessagesEvent.from_update(client=client, update=update)
    if d is not None:
        out.append(d)

    return out

