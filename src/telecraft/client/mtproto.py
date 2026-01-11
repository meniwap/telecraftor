from __future__ import annotations

import asyncio
import time
import types
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from telecraft.client.entities import (
    EntityCache,
    EntityCacheError,
    load_entity_cache_file,
    save_entity_cache_file,
)
from telecraft.client.peers import (
    Peer,
    PeerRef,
    normalize_phone,
    normalize_username,
    parse_peer_ref,
    peer_from_tl_peer,
)
from telecraft.mtproto.auth.handshake import exchange_auth_key
from telecraft.mtproto.auth.server_keys import DEFAULT_SERVER_KEYRING
from telecraft.mtproto.auth.srp import SrpError, make_input_check_password_srp
from telecraft.mtproto.core.msg_id import MsgIdGenerator
from telecraft.mtproto.core.state import MtprotoState
from telecraft.mtproto.rpc.sender import MtprotoEncryptedSender, ReceivedMessage, RpcErrorException
from telecraft.mtproto.session import MtprotoSession, load_session_file, save_session_file
from telecraft.mtproto.transport.abridged import AbridgedFraming
from telecraft.mtproto.transport.base import Endpoint, Framing
from telecraft.mtproto.transport.intermediate import IntermediateFraming
from telecraft.mtproto.transport.tcp import TcpTransport
from telecraft.mtproto.updates.engine import AppliedUpdates, UpdatesEngine
from telecraft.mtproto.updates.state import UpdatesState
from telecraft.schema.pinned_layer import LAYER
from telecraft.tl.generated.functions import (
    AccountGetPassword,
    AuthCheckPassword,
    AuthExportAuthorization,
    AuthImportAuthorization,
    AuthSendCode,
    AuthSignIn,
    AuthSignUp,
    ChannelsEditAdmin,
    ChannelsEditBanned,
    ChannelsInviteToChannel,
    ContactsBlock,
    ContactsGetBlocked,
    ContactsGetContacts,
    ContactsUnblock,
    ContactsResolvePhone,
    ContactsResolveUsername,
    HelpGetConfig,
    InitConnection,
    InvokeWithLayer,
    MessagesAddChatUser,
    ChannelsDeleteMessages,
    ChannelsGetFullChannel,
    ChannelsGetParticipant,
    ChannelsGetParticipants,
    ChannelsJoinChannel,
    ChannelsLeaveChannel,
    MessagesDeleteMessages,
    MessagesCreateChat,
    MessagesDeleteExportedChatInvite,
    MessagesDeleteHistory,
    MessagesEditChatPhoto,
    MessagesEditChatTitle,
    MessagesEditExportedChatInvite,
    MessagesEditMessage,
    MessagesExportChatInvite,
    MessagesForwardMessages,
    MessagesGetCommonChats,
    MessagesGetExportedChatInvites,
    MessagesGetFullChat,
    MessagesDeleteScheduledMessages,
    MessagesGetScheduledHistory,
    MessagesGetPollResults,
    MessagesReadHistory,
    MessagesSearch,
    MessagesSendScheduledMessages,
    MessagesSendVote,
    ChannelsCreateChannel,
    ChannelsReadHistory,
    MessagesSendMedia,
    MessagesSendMessage,
    MessagesSendReaction,
    MessagesSetTyping,
    MessagesGetHistory,
    MessagesUpdatePinnedMessage,
    PhotosGetUserPhotos,
    Ping,
    UsersGetFullUser,
    UsersGetUsers,
)
from telecraft.tl.generated.types import (
    AuthAuthorization,
    AuthAuthorizationSignUpRequired,
    AuthSentCode,
    AuthSentCodePaymentRequired,
    AuthSentCodeSuccess,
    CodeSettings,
    ContactsResolvedPeer,
    ChatAdminRights,
    ChatBannedRights,
    InputUser,
    InputUserSelf,
)


class MtprotoClientError(Exception):
    pass


TEST_DCS: dict[int, tuple[str, int]] = {
    1: ("149.154.175.10", 443),
    2: ("149.154.167.40", 443),
    3: ("149.154.175.117", 443),
}

# Common production DCs (IPv4, port 443).
# Can always be overridden with explicit host/port.
PROD_DCS: dict[int, tuple[str, int]] = {
    1: ("149.154.175.50", 443),
    2: ("149.154.167.51", 443),
    3: ("149.154.175.100", 443),
    4: ("149.154.167.91", 443),
    5: ("91.108.56.130", 443),
}


@dataclass(slots=True)
class ClientInit:
    api_id: int
    api_hash: str | None = None
    device_model: str = "telecraft"
    system_version: str = "telecraft"
    app_version: str = "0.0"
    system_lang_code: str = "en"
    lang_pack: str = ""
    lang_code: str = "en"


def _make_framing(name: str) -> Framing:
    if name == "intermediate":
        return IntermediateFraming()
    if name == "abridged":
        return AbridgedFraming()
    raise MtprotoClientError(f"Unknown framing: {name!r}")


def wrap_with_layer_init(*, query: Any, init: ClientInit) -> Any:
    """
    Wrap a TL request as a "real client" invocation:
      invokeWithLayer(LAYER, initConnection(..., query=<query>))
    """

    return InvokeWithLayer(
        layer=LAYER,
        query=InitConnection(
            flags=0,
            api_id=init.api_id,
            device_model=init.device_model,
            system_version=init.system_version,
            app_version=init.app_version,
            system_lang_code=init.system_lang_code,
            lang_pack=init.lang_pack,
            lang_code=init.lang_code,
            proxy=None,
            params=None,
            query=query,
        ),
    )


class MtprotoClient:
    def __init__(
        self,
        *,
        network: str = "test",
        dc_id: int = 2,
        host: str | None = None,
        port: int = 443,
        framing: str = "intermediate",
        session_path: str | Path | None = None,
        init: ClientInit | None = None,
    ) -> None:
        if network not in {"test", "prod"}:
            raise MtprotoClientError("network must be 'test' or 'prod'")
        self._network = network
        self._dc_id = dc_id
        self._host = host
        self._port = port
        self._framing_name = framing
        self._session_path = Path(session_path) if session_path is not None else None
        self._init = init

        self._transport: TcpTransport | None = None
        self._sender: MtprotoEncryptedSender | None = None
        self._state: MtprotoState | None = None
        self._msg_id_gen: MsgIdGenerator | None = None
        self._did_init_connection: bool = False
        self._incoming: asyncio.Queue[ReceivedMessage] | None = None
        self._updates_engine: UpdatesEngine | None = None
        self._updates_task: asyncio.Task[None] | None = None
        self._updates_out: asyncio.Queue[Any] | None = None
        self._updates_state_last_save: float = 0.0
        self._entities_last_save: float = 0.0
        # Best-effort "me" identity (used by higher-level layers to classify self-authored messages).
        self.self_user_id: int | None = None

        self.config: Any | None = None
        self.entities = EntityCache()
        # Cross-DC helpers for media downloads (lazy).
        self._media_clients: dict[int, MtprotoClient] = {}
        # Entity priming guardrails (avoid spamming dialogs on repeated short updates).
        self._prime_lock = asyncio.Lock()
        self._prime_last_attempt: float = 0.0

    @property
    def is_connected(self) -> bool:
        return self._transport is not None and self._sender is not None and self._state is not None

    def _endpoint(self) -> tuple[str, int]:
        if self._host is not None:
            return self._host, self._port
        mapping = TEST_DCS if self._network == "test" else PROD_DCS
        host, port = mapping.get(self._dc_id, ("", 0))
        if not host:
            raise MtprotoClientError(f"Unknown DC: {self._dc_id} (network={self._network})")
        return host, port

    async def connect(self, *, timeout: float = 30.0) -> None:
        if self.is_connected:
            return

        # If we have a session file, treat it as authoritative for endpoint/framing.
        # This avoids common "session mismatch" errors when a previous login migrated DCs.
        sess: MtprotoSession | None = None
        if self._session_path is not None and self._session_path.exists():
            sess = load_session_file(self._session_path)
            self._dc_id = int(sess.dc_id)
            self._host = str(sess.host)
            self._port = int(sess.port)
            self._framing_name = str(sess.framing)

        host, port = self._endpoint()
        framing = _make_framing(self._framing_name)
        transport = TcpTransport(endpoint=Endpoint(host=host, port=port), framing=framing)
        await transport.connect()

        sender: MtprotoEncryptedSender | None = None
        try:
            auth_key: bytes
            server_salt: bytes

            if sess is not None:
                auth_key = sess.auth_key
                server_salt = sess.server_salt
            else:
                rsa_keys = list(DEFAULT_SERVER_KEYRING.keys_by_fingerprint.values())
                res = await asyncio.wait_for(
                    exchange_auth_key(transport, rsa_keys=rsa_keys),
                    timeout=timeout,
                )
                auth_key = res.auth_key
                server_salt = res.server_salt

            msg_id_gen = MsgIdGenerator()
            state = MtprotoState(
                auth_key=auth_key,
                server_salt=server_salt,
                msg_id_gen=msg_id_gen,
                # NOTE: we intentionally do not persist/reuse session_id across process restarts
                # unless seqno is also persisted.
                session_id=b"",
            )

            incoming: asyncio.Queue[ReceivedMessage] = asyncio.Queue(maxsize=2048)
            sender = MtprotoEncryptedSender(
                transport, state=state, msg_id_gen=msg_id_gen, incoming_queue=incoming
            )

            self._transport = transport
            self._sender = sender
            self._state = state
            self._msg_id_gen = msg_id_gen
            self._incoming = incoming

            # Restore entity cache (enables DM/channel replies after restarts).
            self._load_entities_cache()

            # Bootstrap as a "real" API client.
            if self._init is not None:
                self.config = await self.invoke_with_layer(HelpGetConfig(), timeout=timeout)
                self._did_init_connection = True

            await self._persist_session()
        except Exception:
            if sender is not None:
                await sender.close()
            await transport.close()
            raise

    async def close(self) -> None:
        if not self.is_connected:
            return
        await self._persist_session()
        self._persist_entities_cache(force=True)

        assert self._sender is not None
        assert self._transport is not None
        # Close any auxiliary DC clients (best-effort).
        if self._media_clients:
            for _dc, c in list(self._media_clients.items()):
                try:
                    await c.close()
                except Exception:
                    pass
            self._media_clients.clear()
        await self.stop_updates()
        await self._sender.close()
        await self._transport.close()

        self._sender = None
        self._transport = None
        self._state = None
        self._msg_id_gen = None
        self._incoming = None
        self._updates_engine = None
        self._updates_task = None
        self._updates_out = None

    async def __aenter__(self) -> MtprotoClient:
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: types.TracebackType | None,
    ) -> None:
        await self.close()

    async def invoke(self, req: Any, *, timeout: float = 20.0) -> Any:
        if self._sender is None:
            raise MtprotoClientError("Not connected")
        return await self._sender.invoke_tl(req, timeout=timeout)

    async def invoke_with_layer(self, req: Any, *, timeout: float = 20.0) -> Any:
        if self._init is None:
            raise MtprotoClientError("ClientInit(api_id=...) is required for invoke_with_layer")
        wrapped = wrap_with_layer_init(query=req, init=self._init)
        return await self.invoke(wrapped, timeout=timeout)

    async def invoke_api(self, req: Any, *, timeout: float = 20.0) -> Any:
        """
        Invoke a regular API method after we've performed initConnection/invokeWithLayer once.
        """
        if self._init is not None and not self._did_init_connection:
            # Perform one bootstrap call to "register" the client.
            self.config = await self.invoke_with_layer(HelpGetConfig(), timeout=timeout)
            self._did_init_connection = True
        return await self.invoke(req, timeout=timeout)

    async def ping(self, *, timeout: float = 20.0) -> Any:
        # ping doesn't need initConnection/invokeWithLayer.
        from secrets import randbits

        ping_id = randbits(63)
        return await self.invoke(Ping(ping_id=ping_id), timeout=timeout)

    async def start_updates(self, *, timeout: float = 20.0) -> None:
        """
        Start updates engine and background consumer.

        This must be called after login if you want to receive user updates reliably.
        """
        if self._updates_task is not None:
            return
        if self._incoming is None:
            raise MtprotoClientError("Not connected")
        if self._init is None:
            raise MtprotoClientError("ClientInit(api_id=...) is required to start updates")

        self._updates_out = asyncio.Queue(maxsize=4096)
        self._updates_engine = UpdatesEngine(
            invoke_api=lambda req: self.invoke_api(req, timeout=timeout),
            resolve_input_channel=lambda channel_id: self.entities.input_channel(int(channel_id)),
        )
        initial_state = self._load_updates_state()
        await self._updates_engine.initialize(initial_state=initial_state)
        self._updates_task = asyncio.create_task(self._updates_loop())

    async def stop_updates(self) -> None:
        if self._updates_task is None:
            return
        self._updates_task.cancel()
        try:
            await self._updates_task
        except asyncio.CancelledError:
            pass
        self._updates_task = None
        self._persist_updates_state(force=True)

    async def recv_update(self) -> Any:
        if self._updates_out is None:
            raise MtprotoClientError("Updates not started (call start_updates())")
        return await self._updates_out.get()

    async def _updates_loop(self) -> None:
        assert self._incoming is not None
        assert self._updates_out is not None
        assert self._updates_engine is not None

        while True:
            msg = await self._incoming.get()
            applied: AppliedUpdates = await self._updates_engine.apply(msg.obj)

            self.entities.ingest_users(applied.users)
            self.entities.ingest_chats(applied.chats)
            self._persist_entities_cache()

            # Emit updates and messages separately for now (higher-level mapping later).
            for u in applied.new_messages:
                try:
                    self._updates_out.put_nowait(u)
                except asyncio.QueueFull:
                    break
            for u in applied.updates:
                try:
                    self._updates_out.put_nowait(u)
                except asyncio.QueueFull:
                    break

            self._persist_updates_state()

    def _updates_state_path(self) -> Path | None:
        if self._session_path is None:
            return None
        p = self._session_path
        # Keep "basename" stable:
        #   prod_dc2.session.json -> prod_dc2.updates.json
        if p.name.endswith(".session.json"):
            name = p.name[: -len(".session.json")] + ".updates.json"
            return p.with_name(name)
        return p.with_name(p.name + ".updates.json")

    def _load_updates_state(self) -> UpdatesState | None:
        p = self._updates_state_path()
        if p is None or not p.exists():
            return None
        try:
            from telecraft.mtproto.updates.storage import load_updates_state_file

            return load_updates_state_file(p)
        except Exception:
            # Best-effort: if storage is corrupted/missing fields, start from server getState.
            return None

    def _persist_updates_state(self, *, force: bool = False) -> None:
        p = self._updates_state_path()
        if p is None:
            return
        if self._updates_engine is None or self._updates_engine.state is None:
            return
        now = time.monotonic()
        if not force and (now - self._updates_state_last_save) < 2.0:
            return
        self._updates_state_last_save = now
        try:
            from telecraft.mtproto.updates.storage import save_updates_state_file

            save_updates_state_file(p, self._updates_engine.state)
        except Exception:
            # Best-effort persistence; never break the running client.
            return

    def _entities_path(self) -> Path | None:
        if self._session_path is None:
            return None
        p = self._session_path
        # Keep "basename" stable:
        #   prod_dc2.session.json -> prod_dc2.entities.json
        if p.name.endswith(".session.json"):
            name = p.name[: -len(".session.json")] + ".entities.json"
            return p.with_name(name)
        return p.with_name(p.name + ".entities.json")

    def _load_entities_cache(self) -> None:
        p = self._entities_path()
        if p is None or not p.exists():
            return
        try:
            self.entities = load_entity_cache_file(p)
        except Exception:
            # Best-effort; corrupted cache should not break connect.
            return

    def _persist_entities_cache(self, *, force: bool = False) -> None:
        p = self._entities_path()
        if p is None:
            return
        now = time.monotonic()
        if not force and (now - self._entities_last_save) < 2.0:
            return
        self._entities_last_save = now
        try:
            save_entity_cache_file(p, self.entities)
        except Exception:
            # Best-effort persistence; never break the running client.
            return

    async def get_me(self, *, timeout: float = 20.0) -> Any:
        """
        Fetch current user and update entity cache.

        Returns the User object, or None if not logged in or got UserEmpty.
        """
        res = await self.invoke_api(UsersGetUsers(id=[InputUserSelf()]), timeout=timeout)
        users = res if isinstance(res, list) else []
        self.entities.ingest_users(users)
        self._persist_entities_cache()
        me = users[0] if users else None

        # Check for UserEmpty (returned when not logged in properly)
        if me is not None:
            tl_name = getattr(me, "TL_NAME", None)
            if tl_name == "userEmpty":
                # UserEmpty means we're not properly authenticated
                return None

        mid = getattr(me, "id", None)
        if isinstance(mid, int):
            self.self_user_id = int(mid)
        return me

    async def resolve_username(
        self, username: str, *, timeout: float = 20.0, force: bool = False
    ) -> Peer:
        """
        Resolve @username -> Peer and populate EntityCache (users/chats + username map).
        """
        u = normalize_username(username)
        if not u:
            raise MtprotoClientError("resolve_username: empty username")

        if not force:
            cached = self.entities.peer_from_username(u)
            if cached is not None:
                return cached

        res = await self.invoke_api(
            ContactsResolveUsername(flags=0, username=u, referer=None),
            timeout=timeout,
        )
        if not isinstance(res, ContactsResolvedPeer):
            raise MtprotoClientError(
                f"Unexpected contacts.resolveUsername result: {type(res).__name__}"
            )
        users = cast(list[Any], getattr(res, "users", []))
        chats = cast(list[Any], getattr(res, "chats", []))
        self.entities.ingest_users(list(users))
        self.entities.ingest_chats(list(chats))

        p = peer_from_tl_peer(getattr(res, "peer", None))
        if p is None:
            raise MtprotoClientError("contacts.resolveUsername returned invalid peer")
        # Record the mapping (helps for future resolves without network).
        self.entities.username_to_peer[u] = (p.peer_type, int(p.peer_id))
        self._persist_entities_cache()
        return p

    async def resolve_phone(self, phone: str, *, timeout: float = 20.0, force: bool = False) -> Peer:
        """
        Resolve +phone -> Peer(user) and populate EntityCache.
        """
        ph = normalize_phone(phone)
        if not ph:
            raise MtprotoClientError("resolve_phone: empty phone")

        if not force:
            cached = self.entities.peer_from_phone(ph)
            if cached is not None:
                return cached

        res = await self.invoke_api(ContactsResolvePhone(phone=ph), timeout=timeout)
        if not isinstance(res, ContactsResolvedPeer):
            raise MtprotoClientError(
                f"Unexpected contacts.resolvePhone result: {type(res).__name__}"
            )
        users = cast(list[Any], getattr(res, "users", []))
        chats = cast(list[Any], getattr(res, "chats", []))
        self.entities.ingest_users(list(users))
        self.entities.ingest_chats(list(chats))
        p = peer_from_tl_peer(getattr(res, "peer", None))
        if p is None:
            raise MtprotoClientError("contacts.resolvePhone returned invalid peer")
        if p.peer_type != "user":
            raise MtprotoClientError(f"contacts.resolvePhone returned non-user peer: {p.peer_type}")
        self.entities.phone_to_user_id[ph] = int(p.peer_id)
        self._persist_entities_cache()
        return p

    async def resolve_peer(self, ref: PeerRef, *, timeout: float = 20.0) -> Peer:
        """
        Resolve a high-level peer reference into a Peer.
        """
        if isinstance(ref, Peer):
            return ref
        if isinstance(ref, tuple) and len(ref) == 2 and ref[0] in {"user", "chat", "channel"}:
            return Peer(peer_type=ref[0], peer_id=int(ref[1]))
        if isinstance(ref, str):
            s = ref.strip()
            if not s:
                raise MtprotoClientError("resolve_peer: empty string")
            # Support 'user:123'/'chat:123'/'channel:123' and t.me links.
            try:
                parsed = parse_peer_ref(s)
            except Exception:
                parsed = s
            if isinstance(parsed, tuple):
                return Peer(peer_type=parsed[0], peer_id=int(parsed[1]))
            if isinstance(parsed, str):
                if parsed.startswith("@"):
                    return await self.resolve_username(parsed, timeout=timeout)
                if parsed.startswith("+"):
                    return await self.resolve_phone(parsed, timeout=timeout)
                # digits-only strings are ambiguous: treat as id only if cache knows it.
                if parsed.isdigit():
                    n = int(parsed)
                    if n in self.entities.user_access_hash:
                        return Peer.user(n)
                    if n in self.entities.channel_access_hash:
                        return Peer.channel(n)
                    raise MtprotoClientError(
                        f"resolve_peer: unknown id {n}; "
                        f"use user:{n}/chat:{n}/channel:{n} or @username"
                    )
            raise MtprotoClientError(f"resolve_peer: unsupported string ref: {ref!r}")
        if isinstance(ref, int):
            # Conservative: only accept ints we can classify from cache.
            if int(ref) in self.entities.user_access_hash:
                return Peer.user(int(ref))
            if int(ref) in self.entities.channel_access_hash:
                return Peer.channel(int(ref))
            raise MtprotoClientError(
                f"resolve_peer: unknown id {ref}; pass Peer('chat'|...) or '@username' to resolve"
            )
        raise MtprotoClientError(f"resolve_peer: unsupported ref type: {type(ref).__name__}")

    async def send_message_self(self, text: str, *, timeout: float = 20.0) -> Any:
        """
        Minimal send message to self (no entity resolution needed).
        """
        from telecraft.tl.generated.types import InputPeerSelf

        return await self.send_message_peer(InputPeerSelf(), text, timeout=timeout)

    async def send_message_chat(self, chat_id: int, text: str, *, timeout: float = 20.0) -> Any:
        """
        Send a message to a basic group chat (InputPeerChat doesn't need access_hash).
        """
        from telecraft.tl.generated.types import InputPeerChat

        return await self.send_message_peer(
            InputPeerChat(chat_id=int(chat_id)), text, timeout=timeout
        )

    async def send_message_user(self, user_id: int, text: str, *, timeout: float = 20.0) -> Any:
        """
        Send a message to a user (requires access_hash in the entity cache).
        """
        try:
            peer = self.entities.input_peer_user(int(user_id))
        except EntityCacheError:
            await self._prime_entities_for_reply(want=Peer.user(int(user_id)), timeout=timeout)
            peer = self.entities.input_peer_user(int(user_id))
        return await self.send_message_peer(peer, text, timeout=timeout)

    async def send_message_channel(
        self, channel_id: int, text: str, *, timeout: float = 20.0
    ) -> Any:
        """
        Send a message to a channel/supergroup (requires access_hash in the entity cache).
        """
        try:
            peer = self.entities.input_peer_channel(int(channel_id))
        except EntityCacheError:
            await self._prime_entities_for_reply(want=Peer.channel(int(channel_id)), timeout=timeout)
            peer = self.entities.input_peer_channel(int(channel_id))
        return await self.send_message_peer(peer, text, timeout=timeout)

    async def send_message_peer(
        self,
        peer: Any,
        text: str,
        *,
        reply_to_msg_id: int | None = None,
        silent: bool = False,
        reply_markup: Any | None = None,
        timeout: float = 20.0,
    ) -> Any:
        """
        Low-level sendMessage wrapper for supported InputPeer* types.

        Args:
            peer: InputPeer TL object
            text: Message text
            reply_to_msg_id: Optional message ID to reply to
            silent: Send without notification
            reply_markup: Optional keyboard markup (InlineKeyboard.build() or ReplyKeyboard.build())
            timeout: RPC timeout in seconds
        """
        from secrets import randbits

        from telecraft.tl.generated.types import InputReplyToMessage

        reply_to = None
        if reply_to_msg_id is not None:
            reply_to = InputReplyToMessage(
                flags=0,
                reply_to_msg_id=int(reply_to_msg_id),
                top_msg_id=None,
                reply_to_peer_id=None,
                quote_text=None,
                quote_entities=None,
                quote_offset=None,
                monoforum_peer_id=None,
                todo_item_id=None,
            )

        # Build flags
        msg_flags = 0
        if silent:
            msg_flags |= 32
        if reply_to is not None:
            msg_flags |= 1
        if reply_markup is not None:
            msg_flags |= 4

        res = await self.invoke_api(
            MessagesSendMessage(
                flags=msg_flags,
                no_webpage=False,
                silent=bool(silent),
                background=False,
                clear_draft=False,
                noforwards=False,
                update_stickersets_order=False,
                invert_media=False,
                allow_paid_floodskip=False,
                peer=peer,
                reply_to=reply_to,
                message=text,
                random_id=randbits(63),
                reply_markup=reply_markup,
                entities=None,
                schedule_date=None,
                schedule_repeat_period=None,
                send_as=None,
                quick_reply_shortcut=None,
                effect=None,
                allow_paid_stars=None,
                suggested_post=None,
            ),
            timeout=timeout,
        )
        self._ingest_from_updates_result(res)
        return res

    async def send_message(
        self,
        peer: PeerRef,
        text: str,
        *,
        reply_to_msg_id: int | None = None,
        silent: bool = False,
        reply_markup: Any | None = None,
        timeout: float = 20.0,
    ) -> Any:
        """
        High-level send message:
        - accepts Peer / ('user'|'chat'|'channel', id) / '@username' / '+phone' / cached int id
        - resolves to InputPeer and calls messages.sendMessage

        Args:
            peer: Target peer (can be Peer, tuple, @username, +phone, or cached int id)
            text: Message text
            reply_to_msg_id: Optional message ID to reply to
            silent: Send without notification
            reply_markup: Optional keyboard (use InlineKeyboard or ReplyKeyboard builders)
            timeout: RPC timeout in seconds

        Example with inline keyboard:
            from telecraft.client.keyboards import InlineKeyboard
            kb = InlineKeyboard()
            kb.button("Click", callback_data="click").button("Visit", url="https://t.me")
            await client.send_message(peer, "Hello!", reply_markup=kb.build())
        """
        p = await self.resolve_peer(peer, timeout=timeout)

        async def _build_input_peer() -> Any:
            try:
                return self.entities.input_peer(p)
            except EntityCacheError:
                await self._prime_entities_for_reply(want=p, timeout=timeout)
                return self.entities.input_peer(p)

        async def _refresh_peer_ref() -> None:
            """
            Best-effort refresh when Telegram returns PEER_ID_INVALID.
            Usually indicates stale access_hash / stale cached username->id mapping.
            """
            nonlocal p
            if isinstance(peer, str) and peer.strip():
                try:
                    parsed = parse_peer_ref(peer.strip())
                except Exception:
                    parsed = peer.strip()
                if isinstance(parsed, str):
                    if parsed.startswith("@"):
                        p = await self.resolve_username(parsed, timeout=timeout, force=True)
                        return
                    if parsed.startswith("+"):
                        p = await self.resolve_phone(parsed, timeout=timeout, force=True)
                        return
            # Fallback: priming may refresh access_hash for known peers.
            await self._prime_entities_for_reply(want=p, timeout=timeout)

        input_peer = await _build_input_peer()
        try:
            return await self.send_message_peer(
                input_peer, text, reply_to_msg_id=reply_to_msg_id, silent=silent,
                reply_markup=reply_markup, timeout=timeout
            )
        except RpcErrorException as e:
            if e.message == "PEER_ID_INVALID":
                await _refresh_peer_ref()
                input_peer = await _build_input_peer()
                return await self.send_message_peer(
                    input_peer, text, reply_to_msg_id=reply_to_msg_id, silent=silent,
                    reply_markup=reply_markup, timeout=timeout
                )
            raise

    async def send_file(
        self,
        peer: PeerRef,
        path: str | Path,
        *,
        caption: str | None = None,
        as_photo: bool | None = None,
        reply_to_msg_id: int | None = None,
        silent: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        """
        Media MVP: upload a local file and send it as photo/document.

        Args:
            peer: Target peer
            path: Local file path to upload
            caption: Optional caption text
            as_photo: Force send as photo (auto-detected if None)
            reply_to_msg_id: Optional message ID to reply to
            silent: Send without notification
            timeout: RPC timeout in seconds
        """
        from secrets import randbits

        from telecraft.client.media import default_as_photo, guess_mime_type, upload_file
        from telecraft.tl.generated.types import (
            DocumentAttributeFilename,
            InputMediaUploadedDocument,
            InputMediaUploadedPhoto,
            InputReplyToMessage,
        )

        if not self.is_connected:
            raise MtprotoClientError("Not connected")

        p = Path(path)
        if not p.exists() or not p.is_file():
            raise MtprotoClientError(f"send_file: not a file: {p}")

        if as_photo is None:
            as_photo = default_as_photo(p)

        input_file = await upload_file(
            p,
            invoke_api=self.invoke_api,
            timeout=timeout,
        )

        if as_photo:
            media = InputMediaUploadedPhoto(
                flags=0,
                spoiler=False,
                file=input_file,
                stickers=None,
                ttl_seconds=None,
            )
        else:
            mime = guess_mime_type(p)
            attrs = [DocumentAttributeFilename(file_name=p.name)]
            media = InputMediaUploadedDocument(
                flags=0,
                nosound_video=False,
                force_file=True,
                spoiler=False,
                file=input_file,
                thumb=None,
                mime_type=mime,
                attributes=attrs,
                stickers=None,
                video_cover=None,
                video_timestamp=None,
                ttl_seconds=None,
            )

        reply_to = None
        if reply_to_msg_id is not None:
            reply_to = InputReplyToMessage(
                flags=0,
                reply_to_msg_id=int(reply_to_msg_id),
                top_msg_id=None,
                reply_to_peer_id=None,
                quote_text=None,
                quote_entities=None,
                quote_offset=None,
                monoforum_peer_id=None,
                todo_item_id=None,
            )

        p2 = await self.resolve_peer(peer, timeout=timeout)
        try:
            input_peer = self.entities.input_peer(p2)
        except EntityCacheError:
            await self._prime_entities_for_reply(want=p2, timeout=timeout)
            input_peer = self.entities.input_peer(p2)
        res = await self.invoke_api(
            MessagesSendMedia(
                flags=0,
                silent=bool(silent),
                background=False,
                clear_draft=False,
                noforwards=False,
                update_stickersets_order=False,
                invert_media=False,
                allow_paid_floodskip=False,
                peer=input_peer,
                reply_to=reply_to,
                media=media,
                message=caption or "",
                random_id=randbits(63),
                reply_markup=None,
                entities=None,
                schedule_date=None,
                schedule_repeat_period=None,
                send_as=None,
                quick_reply_shortcut=None,
                effect=None,
                allow_paid_stars=None,
                suggested_post=None,
            ),
            timeout=timeout,
        )
        self._ingest_from_updates_result(res)
        return res

    async def send_album(
        self,
        peer: PeerRef,
        paths: list[str | Path],
        *,
        captions: list[str] | None = None,
        reply_to_msg_id: int | None = None,
        silent: bool = False,
        timeout: float = 60.0,
    ) -> Any:
        """
        Send multiple photos/videos as an album (media group).

        Args:
            peer: Target chat/user
            paths: List of file paths (2-10 files)
            captions: Optional list of captions (same length as paths, or None)
            reply_to_msg_id: Message ID to reply to
            silent: Send without notification
            timeout: Request timeout (longer due to uploads)

        Returns:
            Updates with the sent messages
        """
        from secrets import randbits

        from telecraft.client.media import default_as_photo, guess_mime_type, upload_file
        from telecraft.tl.generated.functions import MessagesSendMultiMedia
        from telecraft.tl.generated.types import (
            DocumentAttributeFilename,
            InputMediaUploadedDocument,
            InputMediaUploadedPhoto,
            InputReplyToMessage,
            InputSingleMedia,
        )

        if len(paths) < 2:
            raise MtprotoClientError("send_album: need at least 2 files")
        if len(paths) > 10:
            raise MtprotoClientError("send_album: maximum 10 files")

        if captions is not None and len(captions) != len(paths):
            raise MtprotoClientError("send_album: captions must match paths length")

        p = await self.resolve_peer(peer, timeout=timeout)
        try:
            input_peer = self.entities.input_peer(p)
        except EntityCacheError:
            await self._prime_entities_for_reply(want=p, timeout=timeout)
            input_peer = self.entities.input_peer(p)

        # Upload all files and build media list
        multi_media: list[Any] = []
        for i, file_path in enumerate(paths):
            fp = Path(file_path)
            if not fp.exists() or not fp.is_file():
                raise MtprotoClientError(f"send_album: not a file: {fp}")

            input_file = await upload_file(
                fp,
                invoke_api=self.invoke_api,
                timeout=timeout,
            )

            is_photo = default_as_photo(fp)
            caption = captions[i] if captions else ""

            if is_photo:
                media = InputMediaUploadedPhoto(
                    flags=0,
                    spoiler=False,
                    file=input_file,
                    stickers=None,
                    ttl_seconds=None,
                )
            else:
                mime = guess_mime_type(fp)
                attrs = [DocumentAttributeFilename(file_name=fp.name)]
                media = InputMediaUploadedDocument(
                    flags=0,
                    nosound_video=False,
                    force_file=False,
                    spoiler=False,
                    file=input_file,
                    thumb=None,
                    mime_type=mime,
                    attributes=attrs,
                    stickers=None,
                    video_cover=None,
                    video_timestamp=None,
                    ttl_seconds=None,
                )

            single = InputSingleMedia(
                flags=0,
                media=media,
                random_id=randbits(63),
                message=caption,
                entities=None,
            )
            multi_media.append(single)

        # Build reply_to
        reply_to = None
        if reply_to_msg_id is not None:
            reply_to = InputReplyToMessage(
                flags=0,
                reply_to_msg_id=int(reply_to_msg_id),
                top_msg_id=None,
                reply_to_peer_id=None,
                quote_text=None,
                quote_entities=None,
                quote_offset=None,
            )

        msg_flags = 0
        if silent:
            msg_flags |= 32
        if reply_to is not None:
            msg_flags |= 1

        res = await self.invoke_api(
            MessagesSendMultiMedia(
                flags=msg_flags,
                silent=silent if silent else None,
                background=None,
                clear_draft=None,
                noforwards=None,
                update_stickersets_order=None,
                invert_media=None,
                allow_paid_floodskip=None,
                peer=input_peer,
                reply_to=reply_to,
                multi_media=multi_media,
                schedule_date=None,
                send_as=None,
                quick_reply_shortcut=None,
                effect=None,
                allow_paid_stars=None,
            ),
            timeout=timeout,
        )
        self._ingest_from_updates_result(res)
        return res

    async def forward_messages(
        self,
        from_peer: PeerRef,
        to_peer: PeerRef,
        msg_ids: list[int] | int,
        *,
        silent: bool = False,
        drop_author: bool = False,
        drop_captions: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        """
        Forward messages from one chat to another.

        Args:
            from_peer: Source peer (where the messages are)
            to_peer: Destination peer (where to forward)
            msg_ids: Single message ID or list of message IDs to forward
            silent: Send without notification
            drop_author: Hide the original author
            drop_captions: Remove captions from media
            timeout: RPC timeout in seconds

        Returns:
            Updates object with the forwarded messages
        """
        from secrets import randbits

        # Normalize msg_ids to list
        if isinstance(msg_ids, int):
            ids = [msg_ids]
        else:
            ids = list(msg_ids)

        if not ids:
            raise MtprotoClientError("forward_messages: msg_ids cannot be empty")

        # Generate random IDs for each message
        random_ids = [randbits(63) for _ in ids]

        # Resolve peers
        from_p = await self.resolve_peer(from_peer, timeout=timeout)
        to_p = await self.resolve_peer(to_peer, timeout=timeout)

        try:
            from_input_peer = self.entities.input_peer(from_p)
        except EntityCacheError:
            await self._prime_entities_for_reply(want=from_p, timeout=timeout)
            from_input_peer = self.entities.input_peer(from_p)

        try:
            to_input_peer = self.entities.input_peer(to_p)
        except EntityCacheError:
            await self._prime_entities_for_reply(want=to_p, timeout=timeout)
            to_input_peer = self.entities.input_peer(to_p)

        res = await self.invoke_api(
            MessagesForwardMessages(
                flags=0,
                silent=bool(silent),
                background=False,
                with_my_score=False,
                drop_author=bool(drop_author),
                drop_media_captions=bool(drop_captions),
                noforwards=False,
                allow_paid_floodskip=False,
                from_peer=from_input_peer,
                id=ids,
                random_id=random_ids,
                to_peer=to_input_peer,
                top_msg_id=None,
                reply_to=None,
                schedule_date=None,
                schedule_repeat_period=None,
                send_as=None,
                quick_reply_shortcut=None,
                effect=None,
                video_timestamp=None,
                allow_paid_stars=None,
                suggested_post=None,
            ),
            timeout=timeout,
        )
        self._ingest_from_updates_result(res)
        return res

    async def delete_messages(
        self,
        peer: PeerRef,
        msg_ids: list[int] | int,
        *,
        revoke: bool = True,
        timeout: float = 20.0,
    ) -> Any:
        """
        Delete messages from a chat.

        Args:
            peer: The chat/channel where messages are located
            msg_ids: Single message ID or list of message IDs to delete
            revoke: If True, delete for everyone; if False, delete only for self
                   (Note: for channels, messages are always deleted for everyone)
            timeout: RPC timeout in seconds

        Returns:
            messages.AffectedMessages with pts and pts_count
        """
        # Normalize msg_ids to list
        if isinstance(msg_ids, int):
            ids = [msg_ids]
        else:
            ids = list(msg_ids)

        if not ids:
            raise MtprotoClientError("delete_messages: msg_ids cannot be empty")

        p = await self.resolve_peer(peer, timeout=timeout)

        # For channels/supergroups, use channels.deleteMessages
        if p.peer_type == "channel":
            try:
                input_channel = self.entities.input_channel(int(p.peer_id))
            except EntityCacheError:
                await self._prime_entities_for_reply(want=p, timeout=timeout)
                input_channel = self.entities.input_channel(int(p.peer_id))

            return await self.invoke_api(
                ChannelsDeleteMessages(channel=input_channel, id=ids),
                timeout=timeout,
            )

        # For regular chats and private messages, use messages.deleteMessages
        return await self.invoke_api(
            MessagesDeleteMessages(flags=0, revoke=bool(revoke), id=ids),
            timeout=timeout,
        )

    async def edit_message(
        self,
        peer: PeerRef,
        msg_id: int,
        text: str | None = None,
        *,
        no_webpage: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        """
        Edit a message's text.

        Args:
            peer: The chat where the message is
            msg_id: Message ID to edit
            text: New text (None to keep unchanged, useful for editing media only)
            no_webpage: Disable link preview
            timeout: RPC timeout in seconds

        Returns:
            Updates object
        """
        p = await self.resolve_peer(peer, timeout=timeout)
        try:
            input_peer = self.entities.input_peer(p)
        except EntityCacheError:
            await self._prime_entities_for_reply(want=p, timeout=timeout)
            input_peer = self.entities.input_peer(p)

        res = await self.invoke_api(
            MessagesEditMessage(
                flags=0,
                no_webpage=bool(no_webpage),
                invert_media=False,
                peer=input_peer,
                id=int(msg_id),
                message=text,
                media=None,
                reply_markup=None,
                entities=None,
                schedule_date=None,
                schedule_repeat_period=None,
                quick_reply_shortcut_id=None,
            ),
            timeout=timeout,
        )
        self._ingest_from_updates_result(res)
        return res

    async def pin_message(
        self,
        peer: PeerRef,
        msg_id: int,
        *,
        silent: bool = False,
        unpin: bool = False,
        pm_oneside: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        """
        Pin or unpin a message in a chat.

        Args:
            peer: The chat where the message is
            msg_id: Message ID to pin/unpin
            silent: Don't notify users about the pin
            unpin: If True, unpin the message instead of pinning
            pm_oneside: Pin only for yourself in a private chat
            timeout: RPC timeout in seconds

        Returns:
            Updates object
        """
        p = await self.resolve_peer(peer, timeout=timeout)
        try:
            input_peer = self.entities.input_peer(p)
        except EntityCacheError:
            await self._prime_entities_for_reply(want=p, timeout=timeout)
            input_peer = self.entities.input_peer(p)

        return await self.invoke_api(
            MessagesUpdatePinnedMessage(
                flags=0,
                silent=bool(silent),
                unpin=bool(unpin),
                pm_oneside=bool(pm_oneside),
                peer=input_peer,
                id=int(msg_id),
            ),
            timeout=timeout,
        )

    async def send_reaction(
        self,
        peer: PeerRef,
        msg_id: int,
        reaction: str | list[str] | None = None,
        *,
        big: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        """
        Add or remove reactions from a message.

        Args:
            peer: The chat where the message is
            msg_id: Message ID to react to
            reaction: Emoji string (e.g. "👍"), list of emojis, or None to remove all reactions
            big: Show big animation
            timeout: RPC timeout in seconds

        Returns:
            Updates object

        Examples:
            await client.send_reaction(peer, msg_id, "👍")  # Add thumbs up
            await client.send_reaction(peer, msg_id, ["👍", "❤️"])  # Multiple reactions
            await client.send_reaction(peer, msg_id, None)  # Remove reactions
        """
        from telecraft.tl.generated.types import ReactionEmoji

        p = await self.resolve_peer(peer, timeout=timeout)
        try:
            input_peer = self.entities.input_peer(p)
        except EntityCacheError:
            await self._prime_entities_for_reply(want=p, timeout=timeout)
            input_peer = self.entities.input_peer(p)

        # Build reaction list
        reactions = None
        if reaction is not None:
            if isinstance(reaction, str):
                reactions = [ReactionEmoji(emoticon=reaction)]
            else:
                reactions = [ReactionEmoji(emoticon=r) for r in reaction]

        return await self.invoke_api(
            MessagesSendReaction(
                flags=0,
                big=bool(big),
                add_to_recent=True,
                peer=input_peer,
                msg_id=int(msg_id),
                reaction=reactions,
            ),
            timeout=timeout,
        )

    async def search_messages(
        self,
        peer: PeerRef,
        query: str = "",
        *,
        limit: int = 100,
        from_user: PeerRef | None = None,
        offset_id: int = 0,
        min_date: int = 0,
        max_date: int = 0,
        timeout: float = 20.0,
    ) -> list[Any]:
        """
        Search messages in a chat.

        Args:
            peer: The chat to search in
            query: Search query string (empty string returns all messages)
            limit: Maximum number of messages to return
            from_user: Filter by sender (optional)
            offset_id: Offset message ID for pagination
            min_date: Minimum message date (Unix timestamp)
            max_date: Maximum message date (Unix timestamp)
            timeout: RPC timeout in seconds

        Returns:
            List of Message objects
        """
        from telecraft.tl.generated.types import (
            InputMessagesFilterEmpty,
            MessagesMessages,
            MessagesMessagesSlice,
            MessagesChannelMessages,
        )

        p = await self.resolve_peer(peer, timeout=timeout)
        try:
            input_peer = self.entities.input_peer(p)
        except EntityCacheError:
            await self._prime_entities_for_reply(want=p, timeout=timeout)
            input_peer = self.entities.input_peer(p)

        # Resolve from_user if provided
        from_input_peer = None
        if from_user is not None:
            from_p = await self.resolve_peer(from_user, timeout=timeout)
            try:
                from_input_peer = self.entities.input_peer(from_p)
            except EntityCacheError:
                await self._prime_entities_for_reply(want=from_p, timeout=timeout)
                from_input_peer = self.entities.input_peer(from_p)

        res = await self.invoke_api(
            MessagesSearch(
                flags=0,
                peer=input_peer,
                q=query,
                from_id=from_input_peer,
                saved_peer_id=None,
                saved_reaction=None,
                top_msg_id=None,
                filter=InputMessagesFilterEmpty(),
                min_date=int(min_date),
                max_date=int(max_date),
                offset_id=int(offset_id),
                add_offset=0,
                limit=int(limit),
                max_id=0,
                min_id=0,
                hash=0,
            ),
            timeout=timeout,
        )

        # Ingest entities
        if isinstance(res, (MessagesMessages, MessagesMessagesSlice, MessagesChannelMessages)):
            users = cast(list[Any], getattr(res, "users", []))
            chats = cast(list[Any], getattr(res, "chats", []))
            self.entities.ingest_users(list(users))
            self.entities.ingest_chats(list(chats))
            self._persist_entities_cache(force=True)
            return list(cast(list[Any], getattr(res, "messages", [])))

        return []

    async def iter_participants(
        self,
        channel: PeerRef,
        *,
        limit: int | None = None,
        filter_type: str = "recent",
        timeout: float = 20.0,
    ) -> AsyncIterator[Any]:
        """
        Async generator that iterates over channel/supergroup participants.

        Args:
            channel: The channel/supergroup to get participants from
            limit: Maximum number of participants to return (None for all)
            filter_type: Filter type - "recent", "admins", "bots", "banned", "kicked"
            timeout: RPC timeout in seconds

        Yields:
            ChannelParticipant objects

        Note:
            This only works for channels/supergroups where you have admin rights
            or the channel is public.
        """
        from telecraft.tl.generated.types import (
            ChannelParticipantsRecent,
            ChannelParticipantsAdmins,
            ChannelParticipantsBots,
            ChannelParticipantsBanned,
            ChannelParticipantsKicked,
            ChannelsChannelParticipants,
            ChannelsChannelParticipantsNotModified,
        )

        # Build filter
        filter_map = {
            "recent": ChannelParticipantsRecent(),
            "admins": ChannelParticipantsAdmins(),
            "bots": ChannelParticipantsBots(),
            "banned": ChannelParticipantsBanned(q=""),
            "kicked": ChannelParticipantsKicked(q=""),
        }
        participant_filter = filter_map.get(filter_type, ChannelParticipantsRecent())

        ch = await self.resolve_peer(channel, timeout=timeout)
        if ch.peer_type != "channel":
            raise MtprotoClientError("iter_participants: peer must be a channel/supergroup")

        try:
            input_channel = self.entities.input_channel(int(ch.peer_id))
        except EntityCacheError:
            await self._prime_entities_for_reply(want=ch, timeout=timeout)
            input_channel = self.entities.input_channel(int(ch.peer_id))

        total_yielded = 0
        offset = 0
        batch_size = 200  # Telegram's max per request

        while True:
            remaining = None
            if limit is not None:
                remaining = limit - total_yielded
                if remaining <= 0:
                    break
                batch_limit = min(batch_size, remaining)
            else:
                batch_limit = batch_size

            res = await self.invoke_api(
                ChannelsGetParticipants(
                    channel=input_channel,
                    filter=participant_filter,
                    offset=offset,
                    limit=batch_limit,
                    hash=0,
                ),
                timeout=timeout,
            )

            if isinstance(res, ChannelsChannelParticipantsNotModified):
                break

            if not isinstance(res, ChannelsChannelParticipants):
                break

            # Ingest entities
            users = cast(list[Any], getattr(res, "users", []))
            chats = cast(list[Any], getattr(res, "chats", []))
            self.entities.ingest_users(list(users))
            self.entities.ingest_chats(list(chats))

            participants = cast(list[Any], getattr(res, "participants", []))
            if not participants:
                break

            for p in participants:
                if limit is not None and total_yielded >= limit:
                    return
                yield p
                total_yielded += 1

            offset += len(participants)

            # If we got fewer than requested, we're done
            if len(participants) < batch_limit:
                break

        self._persist_entities_cache(force=True)

    async def get_user_info(
        self,
        user: PeerRef,
        *,
        timeout: float = 20.0,
    ) -> Any:
        """
        Get full information about a user.

        Args:
            user: The user to get info about
            timeout: RPC timeout in seconds

        Returns:
            users.UserFull object containing:
            - full_user: UserFull with bio, common_chats_count, etc.
            - chats: List of related chats
            - users: List of related users
        """
        u = await self.resolve_peer(user, timeout=timeout)
        if u.peer_type != "user":
            raise MtprotoClientError("get_user_info: peer must be a user")

        try:
            input_user = self.entities.input_user(int(u.peer_id))
        except EntityCacheError:
            await self._prime_entities_for_reply(want=u, timeout=timeout)
            input_user = self.entities.input_user(int(u.peer_id))

        res = await self.invoke_api(
            UsersGetFullUser(id=input_user),
            timeout=timeout,
        )

        # Ingest entities
        users = cast(list[Any], getattr(res, "users", []))
        chats = cast(list[Any], getattr(res, "chats", []))
        self.entities.ingest_users(list(users))
        self.entities.ingest_chats(list(chats))
        self._persist_entities_cache(force=True)

        return res

    async def get_chat_info(
        self,
        chat: PeerRef,
        *,
        timeout: float = 20.0,
    ) -> Any:
        """
        Get full information about a chat or channel.

        Args:
            chat: The chat/channel to get info about
            timeout: RPC timeout in seconds

        Returns:
            messages.ChatFull object containing:
            - full_chat: ChatFull/ChannelFull with description, members count, etc.
            - chats: List of related chats
            - users: List of related users
        """
        p = await self.resolve_peer(chat, timeout=timeout)

        if p.peer_type == "chat":
            res = await self.invoke_api(
                MessagesGetFullChat(chat_id=int(p.peer_id)),
                timeout=timeout,
            )
        elif p.peer_type == "channel":
            try:
                input_channel = self.entities.input_channel(int(p.peer_id))
            except EntityCacheError:
                await self._prime_entities_for_reply(want=p, timeout=timeout)
                input_channel = self.entities.input_channel(int(p.peer_id))

            res = await self.invoke_api(
                ChannelsGetFullChannel(channel=input_channel),
                timeout=timeout,
            )
        else:
            raise MtprotoClientError("get_chat_info: peer must be a chat or channel")

        # Ingest entities
        users = cast(list[Any], getattr(res, "users", []))
        chats = cast(list[Any], getattr(res, "chats", []))
        self.entities.ingest_users(list(users))
        self.entities.ingest_chats(list(chats))
        self._persist_entities_cache(force=True)

        return res

    async def join_channel(
        self,
        channel: PeerRef,
        *,
        timeout: float = 20.0,
    ) -> Any:
        """
        Join a public channel or supergroup.

        Args:
            channel: The channel to join (can be @username or channel ID)
            timeout: RPC timeout in seconds

        Returns:
            Updates object
        """
        ch = await self.resolve_peer(channel, timeout=timeout)
        if ch.peer_type != "channel":
            raise MtprotoClientError("join_channel: peer must be a channel")

        try:
            input_channel = self.entities.input_channel(int(ch.peer_id))
        except EntityCacheError:
            await self._prime_entities_for_reply(want=ch, timeout=timeout)
            input_channel = self.entities.input_channel(int(ch.peer_id))

        res = await self.invoke_api(
            ChannelsJoinChannel(channel=input_channel),
            timeout=timeout,
        )
        self._ingest_from_updates_result(res)
        return res

    async def leave_channel(
        self,
        channel: PeerRef,
        *,
        timeout: float = 20.0,
    ) -> Any:
        """
        Leave a channel or supergroup.

        Args:
            channel: The channel to leave
            timeout: RPC timeout in seconds

        Returns:
            Updates object
        """
        ch = await self.resolve_peer(channel, timeout=timeout)
        if ch.peer_type != "channel":
            raise MtprotoClientError("leave_channel: peer must be a channel")

        try:
            input_channel = self.entities.input_channel(int(ch.peer_id))
        except EntityCacheError:
            await self._prime_entities_for_reply(want=ch, timeout=timeout)
            input_channel = self.entities.input_channel(int(ch.peer_id))

        res = await self.invoke_api(
            ChannelsLeaveChannel(channel=input_channel),
            timeout=timeout,
        )
        self._ingest_from_updates_result(res)
        return res

    async def send_action(
        self,
        peer: PeerRef,
        action: str = "typing",
        *,
        timeout: float = 20.0,
    ) -> bool:
        """
        Send a chat action (typing indicator, etc.)

        Args:
            peer: The chat to send action in
            action: Action type - "typing", "recording_voice", "recording_video",
                   "uploading_photo", "uploading_video", "uploading_document",
                   "choosing_sticker", "playing_game", "cancel"
            timeout: RPC timeout in seconds

        Returns:
            True if successful
        """
        from telecraft.tl.generated.types import (
            SendMessageTypingAction,
            SendMessageRecordAudioAction,
            SendMessageRecordVideoAction,
            SendMessageUploadPhotoAction,
            SendMessageUploadVideoAction,
            SendMessageUploadDocumentAction,
            SendMessageChooseStickerAction,
            SendMessageGamePlayAction,
            SendMessageCancelAction,
        )

        action_map = {
            "typing": SendMessageTypingAction(),
            "recording_voice": SendMessageRecordAudioAction(),
            "recording_video": SendMessageRecordVideoAction(),
            "uploading_photo": SendMessageUploadPhotoAction(progress=0),
            "uploading_video": SendMessageUploadVideoAction(progress=0),
            "uploading_document": SendMessageUploadDocumentAction(progress=0),
            "choosing_sticker": SendMessageChooseStickerAction(),
            "playing_game": SendMessageGamePlayAction(),
            "cancel": SendMessageCancelAction(),
        }

        tl_action = action_map.get(action.lower(), SendMessageTypingAction())

        p = await self.resolve_peer(peer, timeout=timeout)
        try:
            input_peer = self.entities.input_peer(p)
        except EntityCacheError:
            await self._prime_entities_for_reply(want=p, timeout=timeout)
            input_peer = self.entities.input_peer(p)

        res = await self.invoke_api(
            MessagesSetTyping(
                flags=0,
                peer=input_peer,
                top_msg_id=None,
                action=tl_action,
            ),
            timeout=timeout,
        )

        # Result is a Bool
        from telecraft.client.media import _tl_bool
        return _tl_bool(res) is True

    async def get_profile_photos(
        self,
        user: PeerRef,
        *,
        limit: int = 100,
        offset: int = 0,
        timeout: float = 20.0,
    ) -> list[Any]:
        """
        Get a user's profile photos.

        Args:
            user: The user to get photos from
            limit: Maximum number of photos to return
            offset: Number of photos to skip
            timeout: RPC timeout in seconds

        Returns:
            List of Photo objects
        """
        u = await self.resolve_peer(user, timeout=timeout)
        if u.peer_type != "user":
            raise MtprotoClientError("get_profile_photos: peer must be a user")

        try:
            input_user = self.entities.input_user(int(u.peer_id))
        except EntityCacheError:
            await self._prime_entities_for_reply(want=u, timeout=timeout)
            input_user = self.entities.input_user(int(u.peer_id))

        res = await self.invoke_api(
            PhotosGetUserPhotos(
                user_id=input_user,
                offset=int(offset),
                max_id=0,
                limit=int(limit),
            ),
            timeout=timeout,
        )

        # Ingest users
        users = cast(list[Any], getattr(res, "users", []))
        self.entities.ingest_users(list(users))
        self._persist_entities_cache(force=True)

        return list(cast(list[Any], getattr(res, "photos", [])))

    async def upload_profile_photo(
        self,
        path: str | Path,
        *,
        fallback: bool = False,
        timeout: float = 60.0,
    ) -> Any:
        """
        Upload a new profile photo for the current user.

        Args:
            path: Path to the photo file
            fallback: If True, set as fallback photo (shown when main is hidden)
            timeout: Request timeout

        Returns:
            photos.Photo object with the uploaded photo
        """
        from telecraft.client.media import upload_file
        from telecraft.tl.generated.functions import PhotosUploadProfilePhoto

        p = Path(path)
        if not p.exists() or not p.is_file():
            raise MtprotoClientError(f"upload_profile_photo: not a file: {p}")

        input_file = await upload_file(
            p,
            invoke_api=self.invoke_api,
            timeout=timeout,
        )

        flags = 1  # file flag
        if fallback:
            flags |= 8

        res = await self.invoke_api(
            PhotosUploadProfilePhoto(
                flags=flags,
                fallback=fallback if fallback else None,
                bot=None,
                file=input_file,
                video=None,
                video_start_ts=None,
                video_emoji_markup=None,
            ),
            timeout=timeout,
        )
        return res

    async def delete_profile_photos(
        self,
        photo_ids: list[tuple[int, int]] | tuple[int, int],
        *,
        timeout: float = 20.0,
    ) -> list[int]:
        """
        Delete profile photos.

        Args:
            photo_ids: List of (photo_id, access_hash) tuples, or single tuple
            timeout: Request timeout

        Returns:
            List of deleted photo IDs
        """
        from telecraft.tl.generated.functions import PhotosDeletePhotos
        from telecraft.tl.generated.types import InputPhoto

        if isinstance(photo_ids, tuple) and len(photo_ids) == 2 and isinstance(photo_ids[0], int):
            # Single photo
            photo_ids = [photo_ids]  # type: ignore

        input_photos = [
            InputPhoto(id=pid, access_hash=ahash, file_reference=b"")
            for pid, ahash in photo_ids
        ]

        res = await self.invoke_api(
            PhotosDeletePhotos(id=input_photos),
            timeout=timeout,
        )
        return list(res) if res else []

    async def edit_admin(
        self,
        channel: PeerRef,
        user: PeerRef,
        *,
        admin_rights: ChatAdminRights,
        rank: str = "",
        timeout: float = 20.0,
    ) -> Any:
        """
        Admin actions MVP: channels.editAdmin.

        Notes:
        - channel must resolve to a channel/supergroup (InputChannel)
        - user must resolve to a user (InputUser)
        """
        ch = await self.resolve_peer(channel, timeout=timeout)
        if ch.peer_type != "channel":
            raise MtprotoClientError(f"edit_admin: channel must be a channel, got {ch.peer_type}")
        try:
            input_channel = self.entities.input_channel(int(ch.peer_id))
        except EntityCacheError:
            await self._prime_entities_for_reply(want=Peer.channel(int(ch.peer_id)), timeout=timeout)
            input_channel = self.entities.input_channel(int(ch.peer_id))

        u = await self.resolve_peer(user, timeout=timeout)
        if u.peer_type != "user":
            raise MtprotoClientError(f"edit_admin: user must be a user, got {u.peer_type}")
        try:
            input_user: InputUser = self.entities.input_user(int(u.peer_id))
        except EntityCacheError:
            await self._prime_entities_for_reply(want=Peer.user(int(u.peer_id)), timeout=timeout)
            input_user = self.entities.input_user(int(u.peer_id))

        res = await self.invoke_api(
            ChannelsEditAdmin(
                channel=input_channel,
                user_id=input_user,
                admin_rights=admin_rights,
                rank=rank or "",
            ),
            timeout=timeout,
        )
        self._ingest_from_updates_result(res)
        return res

    async def edit_banned(
        self,
        channel: PeerRef,
        participant: PeerRef,
        *,
        banned_rights: ChatBannedRights,
        timeout: float = 20.0,
    ) -> Any:
        """
        Admin actions MVP: channels.editBanned.
        """
        ch = await self.resolve_peer(channel, timeout=timeout)
        if ch.peer_type != "channel":
            raise MtprotoClientError(
                f"edit_banned: channel must be a channel, got {ch.peer_type}"
            )
        try:
            input_channel = self.entities.input_channel(int(ch.peer_id))
        except EntityCacheError:
            await self._prime_entities_for_reply(want=Peer.channel(int(ch.peer_id)), timeout=timeout)
            input_channel = self.entities.input_channel(int(ch.peer_id))

        p = await self.resolve_peer(participant, timeout=timeout)
        try:
            input_participant = self.entities.input_peer(p)
        except EntityCacheError:
            await self._prime_entities_for_reply(want=p, timeout=timeout)
            input_participant = self.entities.input_peer(p)

        res = await self.invoke_api(
            ChannelsEditBanned(
                channel=input_channel,
                participant=input_participant,
                banned_rights=banned_rights,
            ),
            timeout=timeout,
        )
        self._ingest_from_updates_result(res)
        return res

    # ========================== High-level Admin Convenience Methods ==========================

    async def ban_user(
        self,
        channel: PeerRef,
        user: PeerRef,
        *,
        until_date: int = 0,
        timeout: float = 20.0,
    ) -> Any:
        """
        Ban a user from a channel/supergroup.

        Args:
            channel: The channel/supergroup to ban from
            user: The user to ban
            until_date: Unix timestamp until when the ban applies (0 = forever)
            timeout: RPC timeout in seconds

        Returns:
            Updates object
        """
        from telecraft.client.admin import banned_rights_full_ban

        return await self.edit_banned(
            channel,
            user,
            banned_rights=banned_rights_full_ban(until_date=until_date),
            timeout=timeout,
        )

    async def unban_user(
        self,
        channel: PeerRef,
        user: PeerRef,
        *,
        timeout: float = 20.0,
    ) -> Any:
        """
        Unban a user from a channel/supergroup.

        Args:
            channel: The channel/supergroup to unban from
            user: The user to unban
            timeout: RPC timeout in seconds

        Returns:
            Updates object
        """
        from telecraft.client.admin import make_banned_rights

        # All rights False = no restrictions = unbanned
        return await self.edit_banned(
            channel,
            user,
            banned_rights=make_banned_rights(until_date=0),
            timeout=timeout,
        )

    async def kick_user(
        self,
        channel: PeerRef,
        user: PeerRef,
        *,
        timeout: float = 20.0,
    ) -> Any:
        """
        Kick a user from a channel/supergroup (ban and immediately unban).

        The user will be removed but can rejoin (not permanently banned).

        Args:
            channel: The channel/supergroup to kick from
            user: The user to kick
            timeout: RPC timeout in seconds

        Returns:
            Updates object from the unban operation
        """
        # First ban
        await self.ban_user(channel, user, timeout=timeout)
        # Then immediately unban so they can rejoin
        return await self.unban_user(channel, user, timeout=timeout)

    async def promote_admin(
        self,
        channel: PeerRef,
        user: PeerRef,
        *,
        change_info: bool = True,
        post_messages: bool = False,
        edit_messages: bool = False,
        delete_messages: bool = True,
        ban_users: bool = True,
        invite_users: bool = True,
        pin_messages: bool = True,
        add_admins: bool = False,
        anonymous: bool = False,
        manage_call: bool = False,
        manage_topics: bool = True,
        rank: str = "",
        timeout: float = 20.0,
    ) -> Any:
        """
        Promote a user to admin in a channel/supergroup.

        Args:
            channel: The channel/supergroup
            user: The user to promote
            change_info: Can change chat info
            post_messages: Can post messages (channels only)
            edit_messages: Can edit others' messages (channels only)
            delete_messages: Can delete messages
            ban_users: Can ban/unban users
            invite_users: Can invite users
            pin_messages: Can pin messages
            add_admins: Can add other admins
            anonymous: Admin actions are anonymous
            manage_call: Can manage voice chats
            manage_topics: Can manage topics in forums
            rank: Admin title/rank (e.g., "Moderator")
            timeout: RPC timeout in seconds

        Returns:
            Updates object
        """
        from telecraft.client.admin import make_admin_rights

        rights = make_admin_rights(
            change_info=change_info,
            post_messages=post_messages,
            edit_messages=edit_messages,
            delete_messages=delete_messages,
            ban_users=ban_users,
            invite_users=invite_users,
            pin_messages=pin_messages,
            add_admins=add_admins,
            anonymous=anonymous,
            manage_call=manage_call,
            manage_topics=manage_topics,
        )
        return await self.edit_admin(channel, user, admin_rights=rights, rank=rank, timeout=timeout)

    async def demote_admin(
        self,
        channel: PeerRef,
        user: PeerRef,
        *,
        timeout: float = 20.0,
    ) -> Any:
        """
        Demote an admin back to a regular member.

        Args:
            channel: The channel/supergroup
            user: The admin to demote
            timeout: RPC timeout in seconds

        Returns:
            Updates object
        """
        from telecraft.client.admin import make_admin_rights

        # All rights False = regular member
        return await self.edit_admin(
            channel,
            user,
            admin_rights=make_admin_rights(),
            rank="",
            timeout=timeout,
        )

    async def get_chat_member(
        self,
        channel: PeerRef,
        user: PeerRef,
        *,
        timeout: float = 20.0,
    ) -> Any:
        """
        Get information about a specific member in a channel/supergroup.

        Args:
            channel: The channel/supergroup
            user: The user to get info about
            timeout: RPC timeout in seconds

        Returns:
            ChannelParticipant object with member info
        """
        ch = await self.resolve_peer(channel, timeout=timeout)
        if ch.peer_type != "channel":
            raise MtprotoClientError(f"get_chat_member: channel must be a channel, got {ch.peer_type}")

        try:
            input_channel = self.entities.input_channel(int(ch.peer_id))
        except EntityCacheError:
            await self._prime_entities_for_reply(want=Peer.channel(int(ch.peer_id)), timeout=timeout)
            input_channel = self.entities.input_channel(int(ch.peer_id))

        u = await self.resolve_peer(user, timeout=timeout)
        if u.peer_type != "user":
            raise MtprotoClientError(f"get_chat_member: user must be a user, got {u.peer_type}")

        try:
            input_user = self.entities.input_user(int(u.peer_id))
        except EntityCacheError:
            await self._prime_entities_for_reply(want=Peer.user(int(u.peer_id)), timeout=timeout)
            input_user = self.entities.input_user(int(u.peer_id))

        res = await self.invoke_api(
            ChannelsGetParticipant(channel=input_channel, participant=input_user),
            timeout=timeout,
        )

        # Ingest users and chats
        users = cast(list[Any], getattr(res, "users", []))
        chats = cast(list[Any], getattr(res, "chats", []))
        self.entities.ingest_users(list(users))
        self.entities.ingest_chats(list(chats))
        self._persist_entities_cache(force=True)

        return getattr(res, "participant", res)

    # ========================== Block/Unblock Methods ==========================

    async def block_user(
        self,
        user: PeerRef,
        *,
        timeout: float = 20.0,
    ) -> bool:
        """
        Block a user.

        Args:
            user: The user to block
            timeout: RPC timeout in seconds

        Returns:
            True if successful
        """
        u = await self.resolve_peer(user, timeout=timeout)

        try:
            input_peer = self.entities.input_peer(u)
        except EntityCacheError:
            await self._prime_entities_for_reply(want=u, timeout=timeout)
            input_peer = self.entities.input_peer(u)

        res = await self.invoke_api(
            ContactsBlock(flags=0, my_stories_from=False, id=input_peer),
            timeout=timeout,
        )
        return bool(res)

    async def unblock_user(
        self,
        user: PeerRef,
        *,
        timeout: float = 20.0,
    ) -> bool:
        """
        Unblock a user.

        Args:
            user: The user to unblock
            timeout: RPC timeout in seconds

        Returns:
            True if successful
        """
        u = await self.resolve_peer(user, timeout=timeout)

        try:
            input_peer = self.entities.input_peer(u)
        except EntityCacheError:
            await self._prime_entities_for_reply(want=u, timeout=timeout)
            input_peer = self.entities.input_peer(u)

        res = await self.invoke_api(
            ContactsUnblock(flags=0, my_stories_from=False, id=input_peer),
            timeout=timeout,
        )
        return bool(res)

    async def get_blocked_users(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        timeout: float = 20.0,
    ) -> list[Any]:
        """
        Get list of blocked users.

        Args:
            limit: Maximum number of users to return
            offset: Offset for pagination
            timeout: RPC timeout in seconds

        Returns:
            List of blocked user objects
        """
        res = await self.invoke_api(
            ContactsGetBlocked(flags=0, my_stories_from=False, offset=offset, limit=limit),
            timeout=timeout,
        )

        # Ingest users
        users = cast(list[Any], getattr(res, "users", []))
        self.entities.ingest_users(list(users))
        self._persist_entities_cache(force=True)

        return list(getattr(res, "blocked", []))

    # ========================== Contacts Methods ==========================

    async def get_contacts(
        self,
        *,
        timeout: float = 20.0,
    ) -> list[Any]:
        """
        Get list of contacts.

        Args:
            timeout: RPC timeout in seconds

        Returns:
            List of User objects representing contacts
        """
        res = await self.invoke_api(
            ContactsGetContacts(hash=0),
            timeout=timeout,
        )

        # Ingest users
        users = cast(list[Any], getattr(res, "users", []))
        self.entities.ingest_users(list(users))
        self._persist_entities_cache(force=True)

        return list(users)

    # ========================== Invite Links Methods ==========================

    async def create_invite_link(
        self,
        peer: PeerRef,
        *,
        expire_date: int | None = None,
        usage_limit: int | None = None,
        request_needed: bool = False,
        title: str | None = None,
        timeout: float = 20.0,
    ) -> Any:
        """
        Create an invite link for a chat/channel.

        Args:
            peer: The chat/channel to create invite link for
            expire_date: Unix timestamp when the link expires (None = never)
            usage_limit: Maximum number of uses (None = unlimited)
            request_needed: Whether admin approval is required to join
            title: Optional title for the invite link
            timeout: RPC timeout in seconds

        Returns:
            ExportedChatInvite object with the invite link
        """
        p = await self.resolve_peer(peer, timeout=timeout)

        try:
            input_peer = self.entities.input_peer(p)
        except EntityCacheError:
            await self._prime_entities_for_reply(want=p, timeout=timeout)
            input_peer = self.entities.input_peer(p)

        # Build flags
        flags = 0
        if expire_date is not None:
            flags |= 1  # flags.0
        if usage_limit is not None:
            flags |= 2  # flags.1
        if request_needed:
            flags |= 8  # flags.3
        if title is not None:
            flags |= 16  # flags.4

        res = await self.invoke_api(
            MessagesExportChatInvite(
                flags=flags,
                legacy_revoke_permanent=False,
                request_needed=request_needed if request_needed else None,
                peer=input_peer,
                expire_date=expire_date,
                usage_limit=usage_limit,
                title=title,
                subscription_pricing=None,
            ),
            timeout=timeout,
        )
        return res

    async def revoke_invite_link(
        self,
        peer: PeerRef,
        link: str,
        *,
        timeout: float = 20.0,
    ) -> Any:
        """
        Revoke an invite link (make it invalid but keep it in the list).

        Args:
            peer: The chat/channel the link belongs to
            link: The invite link to revoke
            timeout: RPC timeout in seconds

        Returns:
            ExportedChatInvite object with revoked status
        """
        p = await self.resolve_peer(peer, timeout=timeout)

        try:
            input_peer = self.entities.input_peer(p)
        except EntityCacheError:
            await self._prime_entities_for_reply(want=p, timeout=timeout)
            input_peer = self.entities.input_peer(p)

        res = await self.invoke_api(
            MessagesEditExportedChatInvite(
                flags=4,  # flags.2 = revoked
                revoked=True,
                peer=input_peer,
                link=link,
                expire_date=None,
                usage_limit=None,
                request_needed=None,
                title=None,
            ),
            timeout=timeout,
        )
        return res

    async def delete_invite_link(
        self,
        peer: PeerRef,
        link: str,
        *,
        timeout: float = 20.0,
    ) -> bool:
        """
        Delete an invite link permanently.

        Args:
            peer: The chat/channel the link belongs to
            link: The invite link to delete
            timeout: RPC timeout in seconds

        Returns:
            True if successful
        """
        p = await self.resolve_peer(peer, timeout=timeout)

        try:
            input_peer = self.entities.input_peer(p)
        except EntityCacheError:
            await self._prime_entities_for_reply(want=p, timeout=timeout)
            input_peer = self.entities.input_peer(p)

        res = await self.invoke_api(
            MessagesDeleteExportedChatInvite(peer=input_peer, link=link),
            timeout=timeout,
        )
        return bool(res)

    async def get_invite_links(
        self,
        peer: PeerRef,
        *,
        revoked: bool = False,
        limit: int = 100,
        timeout: float = 20.0,
    ) -> list[Any]:
        """
        Get list of invite links for a chat/channel.

        Args:
            peer: The chat/channel to get invite links for
            revoked: If True, get only revoked links
            limit: Maximum number of links to return
            timeout: RPC timeout in seconds

        Returns:
            List of ExportedChatInvite objects
        """
        p = await self.resolve_peer(peer, timeout=timeout)

        try:
            input_peer = self.entities.input_peer(p)
        except EntityCacheError:
            await self._prime_entities_for_reply(want=p, timeout=timeout)
            input_peer = self.entities.input_peer(p)

        # We need our own user ID as admin_id
        if self.self_user_id is None:
            await self.get_me(timeout=timeout)

        if self.self_user_id is None:
            raise MtprotoClientError("get_invite_links: cannot determine self_user_id")

        try:
            input_user = self.entities.input_user(self.self_user_id)
        except EntityCacheError:
            await self._prime_entities_for_reply(want=Peer.user(self.self_user_id), timeout=timeout)
            input_user = self.entities.input_user(self.self_user_id)

        flags = 0
        if revoked:
            flags |= 8  # flags.3

        res = await self.invoke_api(
            MessagesGetExportedChatInvites(
                flags=flags,
                revoked=revoked if revoked else None,
                peer=input_peer,
                admin_id=input_user,
                offset_date=None,
                offset_link=None,
                limit=limit,
            ),
            timeout=timeout,
        )

        # Ingest users
        users = cast(list[Any], getattr(res, "users", []))
        self.entities.ingest_users(list(users))
        self._persist_entities_cache(force=True)

        return list(getattr(res, "invites", []))

    # ========================== Group/Channel Creation & Management ==========================

    async def create_group(
        self,
        title: str,
        users: list[PeerRef],
        *,
        timeout: float = 20.0,
    ) -> Any:
        """
        Create a new basic group.

        Args:
            title: Group title
            users: List of users to add to the group
            timeout: RPC timeout in seconds

        Returns:
            InvitedUsers object with the created chat
        """
        input_users: list[Any] = []
        for user_ref in users:
            u = await self.resolve_peer(user_ref, timeout=timeout)
            if u.peer_type != "user":
                raise MtprotoClientError(f"create_group: all members must be users, got {u.peer_type}")
            try:
                input_user = self.entities.input_user(int(u.peer_id))
            except EntityCacheError:
                await self._prime_entities_for_reply(want=Peer.user(int(u.peer_id)), timeout=timeout)
                input_user = self.entities.input_user(int(u.peer_id))
            input_users.append(input_user)

        res = await self.invoke_api(
            MessagesCreateChat(flags=0, users=input_users, title=title, ttl_period=None),
            timeout=timeout,
        )
        self._ingest_from_updates_result(res)
        return res

    async def create_channel(
        self,
        title: str,
        about: str = "",
        *,
        broadcast: bool = True,
        megagroup: bool = False,
        forum: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        """
        Create a new channel or supergroup.

        Args:
            title: Channel/supergroup title
            about: Description
            broadcast: True for channel, False for supergroup
            megagroup: True for supergroup (alternative to broadcast=False)
            forum: True to enable forum/topics
            timeout: RPC timeout in seconds

        Returns:
            Updates object with the created channel
        """
        flags = 0
        if broadcast:
            flags |= 1  # flags.0
        if megagroup:
            flags |= 2  # flags.1
        if forum:
            flags |= 32  # flags.5

        res = await self.invoke_api(
            ChannelsCreateChannel(
                flags=flags,
                broadcast=broadcast if broadcast else None,
                megagroup=megagroup if megagroup else None,
                for_import=None,
                forum=forum if forum else None,
                title=title,
                about=about,
                geo_point=None,
                address=None,
                ttl_period=None,
            ),
            timeout=timeout,
        )
        self._ingest_from_updates_result(res)
        return res

    async def set_chat_title(
        self,
        peer: PeerRef,
        title: str,
        *,
        timeout: float = 20.0,
    ) -> Any:
        """
        Change the title of a group/channel.

        Args:
            peer: The group/channel to rename
            title: New title
            timeout: RPC timeout in seconds

        Returns:
            Updates object
        """
        from telecraft.tl.generated.functions import ChannelsEditTitle

        p = await self.resolve_peer(peer, timeout=timeout)

        if p.peer_type == "chat":
            res = await self.invoke_api(
                MessagesEditChatTitle(chat_id=int(p.peer_id), title=title),
                timeout=timeout,
            )
        elif p.peer_type == "channel":
            try:
                input_channel = self.entities.input_channel(int(p.peer_id))
            except EntityCacheError:
                await self._prime_entities_for_reply(want=Peer.channel(int(p.peer_id)), timeout=timeout)
                input_channel = self.entities.input_channel(int(p.peer_id))

            res = await self.invoke_api(
                ChannelsEditTitle(channel=input_channel, title=title),
                timeout=timeout,
            )
        else:
            raise MtprotoClientError(f"set_chat_title: peer must be a group/channel, got {p.peer_type}")

        self._ingest_from_updates_result(res)
        return res

    async def get_common_chats(
        self,
        user: PeerRef,
        *,
        limit: int = 100,
        timeout: float = 20.0,
    ) -> list[Any]:
        """
        Get chats in common with a user.

        Args:
            user: The user to check
            limit: Maximum number of chats to return
            timeout: RPC timeout in seconds

        Returns:
            List of Chat objects
        """
        u = await self.resolve_peer(user, timeout=timeout)
        if u.peer_type != "user":
            raise MtprotoClientError(f"get_common_chats: peer must be a user, got {u.peer_type}")

        try:
            input_user = self.entities.input_user(int(u.peer_id))
        except EntityCacheError:
            await self._prime_entities_for_reply(want=Peer.user(int(u.peer_id)), timeout=timeout)
            input_user = self.entities.input_user(int(u.peer_id))

        res = await self.invoke_api(
            MessagesGetCommonChats(user_id=input_user, max_id=0, limit=limit),
            timeout=timeout,
        )

        chats = cast(list[Any], getattr(res, "chats", []))
        self.entities.ingest_chats(list(chats))
        self._persist_entities_cache(force=True)

        return list(chats)

    async def mark_read(
        self,
        peer: PeerRef,
        *,
        max_id: int = 0,
        timeout: float = 20.0,
    ) -> Any:
        """
        Mark messages as read in a chat.

        Args:
            peer: The chat to mark as read
            max_id: Mark all messages up to this ID as read (0 = all)
            timeout: RPC timeout in seconds

        Returns:
            AffectedMessages or Bool depending on chat type
        """
        p = await self.resolve_peer(peer, timeout=timeout)

        if p.peer_type == "channel":
            try:
                input_channel = self.entities.input_channel(int(p.peer_id))
            except EntityCacheError:
                await self._prime_entities_for_reply(want=Peer.channel(int(p.peer_id)), timeout=timeout)
                input_channel = self.entities.input_channel(int(p.peer_id))

            return await self.invoke_api(
                ChannelsReadHistory(channel=input_channel, max_id=max_id),
                timeout=timeout,
            )
        else:
            try:
                input_peer = self.entities.input_peer(p)
            except EntityCacheError:
                await self._prime_entities_for_reply(want=p, timeout=timeout)
                input_peer = self.entities.input_peer(p)

            return await self.invoke_api(
                MessagesReadHistory(peer=input_peer, max_id=max_id),
                timeout=timeout,
            )

    async def delete_chat_history(
        self,
        peer: PeerRef,
        *,
        just_clear: bool = True,
        revoke: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        """
        Delete chat history.

        Args:
            peer: The chat to delete history from
            just_clear: If True, only clear history locally (keep for other party)
            revoke: If True, delete for everyone
            timeout: RPC timeout in seconds

        Returns:
            AffectedHistory object
        """
        p = await self.resolve_peer(peer, timeout=timeout)

        try:
            input_peer = self.entities.input_peer(p)
        except EntityCacheError:
            await self._prime_entities_for_reply(want=p, timeout=timeout)
            input_peer = self.entities.input_peer(p)

        flags = 0
        if just_clear:
            flags |= 1  # flags.0
        if revoke:
            flags |= 2  # flags.1

        return await self.invoke_api(
            MessagesDeleteHistory(
                flags=flags,
                just_clear=just_clear if just_clear else None,
                revoke=revoke if revoke else None,
                peer=input_peer,
                max_id=0,
                min_date=None,
                max_date=None,
            ),
            timeout=timeout,
        )

    # ========================== Chat Folders ==========================

    async def get_folders(self, *, timeout: float = 20.0) -> list[Any]:
        """
        Get all chat folders (dialog filters).

        Returns:
            List of DialogFilter objects
        """
        from telecraft.tl.generated.functions import MessagesGetDialogFilters

        res = await self.invoke_api(
            MessagesGetDialogFilters(),
            timeout=timeout,
        )
        return list(getattr(res, "filters", []))

    async def create_folder(
        self,
        title: str,
        *,
        folder_id: int | None = None,
        emoticon: str | None = None,
        contacts: bool = False,
        non_contacts: bool = False,
        groups: bool = False,
        channels: bool = False,
        bots: bool = False,
        exclude_muted: bool = False,
        exclude_read: bool = False,
        exclude_archived: bool = True,
        include_peers: list[PeerRef] | None = None,
        exclude_peers: list[PeerRef] | None = None,
        pinned_peers: list[PeerRef] | None = None,
        timeout: float = 20.0,
    ) -> bool:
        """
        Create a new chat folder.

        Args:
            title: Folder title
            folder_id: Optional folder ID (auto-generated if not provided)
            emoticon: Folder icon emoji
            contacts: Include contacts
            non_contacts: Include non-contacts
            groups: Include groups
            channels: Include channels/broadcasts
            bots: Include bots
            exclude_muted: Exclude muted chats
            exclude_read: Exclude read chats
            exclude_archived: Exclude archived chats
            include_peers: Specific chats to include
            exclude_peers: Specific chats to exclude
            pinned_peers: Chats to pin at top

        Returns:
            True if successful
        """
        from telecraft.tl.generated.functions import MessagesUpdateDialogFilter
        from telecraft.tl.generated.types import DialogFilter, TextWithEntities

        # Auto-generate folder ID if not provided
        if folder_id is None:
            import random
            folder_id = random.randint(2, 255)

        # Build flags
        flags = 0
        if contacts:
            flags |= 1
        if non_contacts:
            flags |= 2
        if groups:
            flags |= 4
        if channels:
            flags |= 8
        if bots:
            flags |= 16
        if exclude_muted:
            flags |= 2048
        if exclude_read:
            flags |= 4096
        if exclude_archived:
            flags |= 8192
        if emoticon is not None:
            flags |= 33554432  # bit 25

        # Resolve peers
        include_input_peers: list[Any] = []
        exclude_input_peers: list[Any] = []
        pinned_input_peers: list[Any] = []

        if include_peers:
            for peer_ref in include_peers:
                p = await self.resolve_peer(peer_ref, timeout=timeout)
                try:
                    include_input_peers.append(self.entities.input_peer(p))
                except EntityCacheError:
                    pass

        if exclude_peers:
            for peer_ref in exclude_peers:
                p = await self.resolve_peer(peer_ref, timeout=timeout)
                try:
                    exclude_input_peers.append(self.entities.input_peer(p))
                except EntityCacheError:
                    pass

        if pinned_peers:
            for peer_ref in pinned_peers:
                p = await self.resolve_peer(peer_ref, timeout=timeout)
                try:
                    pinned_input_peers.append(self.entities.input_peer(p))
                except EntityCacheError:
                    pass

        dialog_filter = DialogFilter(
            flags=flags,
            contacts=contacts if contacts else None,
            non_contacts=non_contacts if non_contacts else None,
            groups=groups if groups else None,
            broadcasts=channels if channels else None,
            bots=bots if bots else None,
            exclude_muted=exclude_muted if exclude_muted else None,
            exclude_read=exclude_read if exclude_read else None,
            exclude_archived=exclude_archived if exclude_archived else None,
            title_noanimate=None,
            id=folder_id,
            title=TextWithEntities(text=title, entities=[]),
            emoticon=emoticon,
            color=None,
            pinned_peers=pinned_input_peers,
            include_peers=include_input_peers,
            exclude_peers=exclude_input_peers,
        )

        return await self.invoke_api(
            MessagesUpdateDialogFilter(
                flags=1,  # filter present
                id=folder_id,
                filter=dialog_filter,
            ),
            timeout=timeout,
        )

    async def delete_folder(self, folder_id: int, *, timeout: float = 20.0) -> bool:
        """
        Delete a chat folder.

        Args:
            folder_id: The folder ID to delete

        Returns:
            True if successful
        """
        from telecraft.tl.generated.functions import MessagesUpdateDialogFilter

        return await self.invoke_api(
            MessagesUpdateDialogFilter(
                flags=0,  # no filter = delete
                id=folder_id,
                filter=None,
            ),
            timeout=timeout,
        )

    async def reorder_folders(
        self, folder_ids: list[int], *, timeout: float = 20.0
    ) -> bool:
        """
        Reorder chat folders.

        Args:
            folder_ids: List of folder IDs in desired order

        Returns:
            True if successful
        """
        from telecraft.tl.generated.functions import MessagesUpdateDialogFiltersOrder

        return await self.invoke_api(
            MessagesUpdateDialogFiltersOrder(order=folder_ids),
            timeout=timeout,
        )

    # ========================== Scheduled Messages ==========================

    async def get_scheduled_messages(
        self,
        peer: PeerRef,
        *,
        timeout: float = 20.0,
    ) -> list[Any]:
        """
        Get list of scheduled messages in a chat.

        Args:
            peer: The chat to get scheduled messages from
            timeout: RPC timeout in seconds

        Returns:
            List of scheduled Message objects
        """
        p = await self.resolve_peer(peer, timeout=timeout)

        try:
            input_peer = self.entities.input_peer(p)
        except EntityCacheError:
            await self._prime_entities_for_reply(want=p, timeout=timeout)
            input_peer = self.entities.input_peer(p)

        res = await self.invoke_api(
            MessagesGetScheduledHistory(peer=input_peer, hash=0),
            timeout=timeout,
        )

        # Ingest users/chats
        users = cast(list[Any], getattr(res, "users", []))
        chats = cast(list[Any], getattr(res, "chats", []))
        self.entities.ingest_users(list(users))
        self.entities.ingest_chats(list(chats))
        self._persist_entities_cache(force=True)

        return list(getattr(res, "messages", []))

    async def delete_scheduled_messages(
        self,
        peer: PeerRef,
        msg_ids: int | list[int],
        *,
        timeout: float = 20.0,
    ) -> Any:
        """
        Delete/cancel scheduled messages.

        Args:
            peer: The chat containing the scheduled messages
            msg_ids: Message ID(s) to delete
            timeout: RPC timeout in seconds

        Returns:
            Updates object
        """
        p = await self.resolve_peer(peer, timeout=timeout)

        try:
            input_peer = self.entities.input_peer(p)
        except EntityCacheError:
            await self._prime_entities_for_reply(want=p, timeout=timeout)
            input_peer = self.entities.input_peer(p)

        ids = [msg_ids] if isinstance(msg_ids, int) else list(msg_ids)

        return await self.invoke_api(
            MessagesDeleteScheduledMessages(peer=input_peer, id=ids),
            timeout=timeout,
        )

    async def send_scheduled_now(
        self,
        peer: PeerRef,
        msg_ids: int | list[int],
        *,
        timeout: float = 20.0,
    ) -> Any:
        """
        Send scheduled messages immediately (before their scheduled time).

        Args:
            peer: The chat containing the scheduled messages
            msg_ids: Message ID(s) to send now
            timeout: RPC timeout in seconds

        Returns:
            Updates object
        """
        p = await self.resolve_peer(peer, timeout=timeout)

        try:
            input_peer = self.entities.input_peer(p)
        except EntityCacheError:
            await self._prime_entities_for_reply(want=p, timeout=timeout)
            input_peer = self.entities.input_peer(p)

        ids = [msg_ids] if isinstance(msg_ids, int) else list(msg_ids)

        return await self.invoke_api(
            MessagesSendScheduledMessages(peer=input_peer, id=ids),
            timeout=timeout,
        )

    # ========================== Location ==========================

    async def send_location(
        self,
        peer: PeerRef,
        latitude: float,
        longitude: float,
        *,
        accuracy_radius: int | None = None,
        reply_to_msg_id: int | None = None,
        silent: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        """
        Send a static location.

        Args:
            peer: Target chat/user
            latitude: Latitude in degrees (-90 to 90)
            longitude: Longitude in degrees (-180 to 180)
            accuracy_radius: Accuracy radius in meters (optional)
            reply_to_msg_id: Message ID to reply to
            silent: Send without notification
            timeout: Request timeout
        """
        from telecraft.tl.generated.types import (
            InputGeoPoint,
            InputMediaGeoPoint,
            InputReplyToMessage,
        )

        p = await self.resolve_peer(peer, timeout=timeout)
        try:
            input_peer = self.entities.input_peer(p)
        except EntityCacheError:
            await self._prime_entities_for_reply(want=p, timeout=timeout)
            input_peer = self.entities.input_peer(p)

        # Build geo point
        geo_flags = 0
        if accuracy_radius is not None:
            geo_flags |= 1

        geo_point = InputGeoPoint(
            flags=geo_flags,
            lat=latitude,
            long=longitude,
            accuracy_radius=accuracy_radius,
        )

        media = InputMediaGeoPoint(geo_point=geo_point)

        # Build message flags
        msg_flags = 0
        if silent:
            msg_flags |= 32
        if reply_to_msg_id is not None:
            msg_flags |= 1

        reply_to = None
        if reply_to_msg_id is not None:
            reply_to = InputReplyToMessage(
                flags=0,
                reply_to_msg_id=reply_to_msg_id,
                top_msg_id=None,
                reply_to_peer_id=None,
                quote_text=None,
                quote_entities=None,
                quote_offset=None,
            )

        import random

        res = await self.invoke_api(
            MessagesSendMedia(
                flags=msg_flags,
                silent=silent if silent else None,
                background=None,
                clear_draft=None,
                noforwards=None,
                update_stickersets_order=None,
                invert_media=None,
                allow_paid_floodskip=None,
                peer=input_peer,
                reply_to=reply_to,
                media=media,
                message="",
                random_id=random.randint(1, 2**63 - 1),
                reply_markup=None,
                entities=None,
                schedule_date=None,
                schedule_repeat_period=None,
                send_as=None,
                quick_reply_shortcut=None,
                effect=None,
                allow_paid_stars=None,
                suggested_post=None,
            ),
            timeout=timeout,
        )
        self._ingest_from_updates_result(res)
        return res

    async def send_live_location(
        self,
        peer: PeerRef,
        latitude: float,
        longitude: float,
        *,
        period: int = 900,
        heading: int | None = None,
        proximity_notification_radius: int | None = None,
        accuracy_radius: int | None = None,
        reply_to_msg_id: int | None = None,
        silent: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        """
        Send a live location that updates in real-time.

        Args:
            peer: Target chat/user
            latitude: Initial latitude
            longitude: Initial longitude
            period: Validity period in seconds (60-86400, default 900 = 15 min)
            heading: Direction heading (0-360 degrees)
            proximity_notification_radius: Distance for proximity alerts (meters)
            accuracy_radius: Accuracy radius in meters
            reply_to_msg_id: Message ID to reply to
            silent: Send without notification
        """
        from telecraft.tl.generated.types import (
            InputGeoPoint,
            InputMediaGeoLive,
            InputReplyToMessage,
        )

        p = await self.resolve_peer(peer, timeout=timeout)
        try:
            input_peer = self.entities.input_peer(p)
        except EntityCacheError:
            await self._prime_entities_for_reply(want=p, timeout=timeout)
            input_peer = self.entities.input_peer(p)

        # Build geo point
        geo_flags = 0
        if accuracy_radius is not None:
            geo_flags |= 1

        geo_point = InputGeoPoint(
            flags=geo_flags,
            lat=latitude,
            long=longitude,
            accuracy_radius=accuracy_radius,
        )

        # Build live location media
        live_flags = 0
        if period is not None:
            live_flags |= 2
        if heading is not None:
            live_flags |= 4
        if proximity_notification_radius is not None:
            live_flags |= 8

        media = InputMediaGeoLive(
            flags=live_flags,
            stopped=None,
            geo_point=geo_point,
            heading=heading,
            period=period,
            proximity_notification_radius=proximity_notification_radius,
        )

        msg_flags = 0
        if silent:
            msg_flags |= 32
        if reply_to_msg_id is not None:
            msg_flags |= 1

        reply_to = None
        if reply_to_msg_id is not None:
            reply_to = InputReplyToMessage(
                flags=0,
                reply_to_msg_id=reply_to_msg_id,
                top_msg_id=None,
                reply_to_peer_id=None,
                quote_text=None,
                quote_entities=None,
                quote_offset=None,
            )

        import random

        res = await self.invoke_api(
            MessagesSendMedia(
                flags=msg_flags,
                silent=silent if silent else None,
                background=None,
                clear_draft=None,
                noforwards=None,
                update_stickersets_order=None,
                invert_media=None,
                allow_paid_floodskip=None,
                peer=input_peer,
                reply_to=reply_to,
                media=media,
                message="",
                random_id=random.randint(1, 2**63 - 1),
                reply_markup=None,
                entities=None,
                schedule_date=None,
                schedule_repeat_period=None,
                send_as=None,
                quick_reply_shortcut=None,
                effect=None,
                allow_paid_stars=None,
                suggested_post=None,
            ),
            timeout=timeout,
        )
        self._ingest_from_updates_result(res)
        return res

    async def stop_live_location(
        self,
        peer: PeerRef,
        msg_id: int,
        *,
        timeout: float = 20.0,
    ) -> Any:
        """
        Stop a live location by editing the message.

        Args:
            peer: Chat where the live location was sent
            msg_id: Message ID of the live location
        """
        from telecraft.tl.generated.types import (
            InputGeoPointEmpty,
            InputMediaGeoLive,
        )

        p = await self.resolve_peer(peer, timeout=timeout)
        try:
            input_peer = self.entities.input_peer(p)
        except EntityCacheError:
            await self._prime_entities_for_reply(want=p, timeout=timeout)
            input_peer = self.entities.input_peer(p)

        # Create stopped live location media
        media = InputMediaGeoLive(
            flags=1,  # stopped flag
            stopped=True,
            geo_point=InputGeoPointEmpty(),
            heading=None,
            period=None,
            proximity_notification_radius=None,
        )

        res = await self.invoke_api(
            MessagesEditMessage(
                flags=16384,  # media flag
                no_webpage=None,
                invert_media=None,
                peer=input_peer,
                id=msg_id,
                message=None,
                media=media,
                reply_markup=None,
                entities=None,
                schedule_date=None,
                schedule_repeat_period=None,
                quick_reply_shortcut_id=None,
            ),
            timeout=timeout,
        )
        self._ingest_from_updates_result(res)
        return res

    # ========================== Contacts ==========================

    async def send_contact(
        self,
        peer: PeerRef,
        phone_number: str,
        first_name: str,
        last_name: str = "",
        vcard: str = "",
        *,
        reply_to_msg_id: int | None = None,
        silent: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        """
        Send a contact to a chat.

        Args:
            peer: Target chat/user
            phone_number: Contact's phone number
            first_name: Contact's first name
            last_name: Contact's last name
            vcard: vCard data (optional)
            reply_to_msg_id: Message to reply to
            silent: Send without notification
        """
        from telecraft.tl.generated.types import (
            InputMediaContact,
            InputReplyToMessage,
        )

        p = await self.resolve_peer(peer, timeout=timeout)
        try:
            input_peer = self.entities.input_peer(p)
        except EntityCacheError:
            await self._prime_entities_for_reply(want=p, timeout=timeout)
            input_peer = self.entities.input_peer(p)

        media = InputMediaContact(
            phone_number=phone_number,
            first_name=first_name,
            last_name=last_name,
            vcard=vcard,
        )

        msg_flags = 0
        if silent:
            msg_flags |= 32
        if reply_to_msg_id is not None:
            msg_flags |= 1

        reply_to = None
        if reply_to_msg_id is not None:
            reply_to = InputReplyToMessage(
                flags=0,
                reply_to_msg_id=reply_to_msg_id,
                top_msg_id=None,
                reply_to_peer_id=None,
                quote_text=None,
                quote_entities=None,
                quote_offset=None,
            )

        import random

        res = await self.invoke_api(
            MessagesSendMedia(
                flags=msg_flags,
                silent=silent if silent else None,
                background=None,
                clear_draft=None,
                noforwards=None,
                update_stickersets_order=None,
                invert_media=None,
                allow_paid_floodskip=None,
                peer=input_peer,
                reply_to=reply_to,
                media=media,
                message="",
                random_id=random.randint(1, 2**63 - 1),
                reply_markup=None,
                entities=None,
                schedule_date=None,
                schedule_repeat_period=None,
                send_as=None,
                quick_reply_shortcut=None,
                effect=None,
                allow_paid_stars=None,
                suggested_post=None,
            ),
            timeout=timeout,
        )
        self._ingest_from_updates_result(res)
        return res

    # ========================== Stickers ==========================

    async def get_sticker_set(
        self,
        short_name: str,
        *,
        timeout: float = 20.0,
    ) -> Any:
        """
        Get a sticker set by short name.

        Args:
            short_name: The short name of the sticker set (e.g., "Animals")

        Returns:
            messages.StickerSet with stickers and documents
        """
        from telecraft.tl.generated.types import InputStickerSetShortName
        from telecraft.tl.generated.functions import MessagesGetStickerSet

        sticker_set = InputStickerSetShortName(short_name=short_name)

        return await self.invoke_api(
            MessagesGetStickerSet(stickerset=sticker_set, hash=0),
            timeout=timeout,
        )

    async def send_sticker(
        self,
        peer: PeerRef,
        sticker_id: int,
        sticker_access_hash: int,
        sticker_file_reference: bytes,
        *,
        reply_to_msg_id: int | None = None,
        silent: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        """
        Send a sticker from an existing sticker set.

        To get sticker info, use get_sticker_set() first, then extract
        document.id, document.access_hash, document.file_reference from
        the documents in the result.

        Args:
            peer: Target chat/user
            sticker_id: Document ID of the sticker
            sticker_access_hash: Access hash of the sticker
            sticker_file_reference: File reference of the sticker
            reply_to_msg_id: Message to reply to
            silent: Send without notification
        """
        from telecraft.tl.generated.types import (
            InputDocument,
            InputMediaDocument,
            InputReplyToMessage,
        )

        p = await self.resolve_peer(peer, timeout=timeout)
        try:
            input_peer = self.entities.input_peer(p)
        except EntityCacheError:
            await self._prime_entities_for_reply(want=p, timeout=timeout)
            input_peer = self.entities.input_peer(p)

        input_doc = InputDocument(
            id=sticker_id,
            access_hash=sticker_access_hash,
            file_reference=sticker_file_reference,
        )

        media = InputMediaDocument(
            flags=0,
            spoiler=None,
            id=input_doc,
            video_cover=None,
            video_timestamp=None,
            ttl_seconds=None,
            query=None,
        )

        msg_flags = 0
        if silent:
            msg_flags |= 32
        if reply_to_msg_id is not None:
            msg_flags |= 1

        reply_to = None
        if reply_to_msg_id is not None:
            reply_to = InputReplyToMessage(
                flags=0,
                reply_to_msg_id=reply_to_msg_id,
                top_msg_id=None,
                reply_to_peer_id=None,
                quote_text=None,
                quote_entities=None,
                quote_offset=None,
            )

        import random

        res = await self.invoke_api(
            MessagesSendMedia(
                flags=msg_flags,
                silent=silent if silent else None,
                background=None,
                clear_draft=None,
                noforwards=None,
                update_stickersets_order=None,
                invert_media=None,
                allow_paid_floodskip=None,
                peer=input_peer,
                reply_to=reply_to,
                media=media,
                message="",
                random_id=random.randint(1, 2**63 - 1),
                reply_markup=None,
                entities=None,
                schedule_date=None,
                schedule_repeat_period=None,
                send_as=None,
                quick_reply_shortcut=None,
                effect=None,
                allow_paid_stars=None,
                suggested_post=None,
            ),
            timeout=timeout,
        )
        self._ingest_from_updates_result(res)
        return res

    # ========================== Dice & Games ==========================

    async def send_dice(
        self,
        peer: PeerRef,
        emoji: str = "🎲",
        *,
        reply_to_msg_id: int | None = None,
        silent: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        """
        Send a dice/game message with animated random result.

        Supported emoji:
        - 🎲 (dice) - values 1-6
        - 🎯 (darts) - values 1-6 (6 = bullseye)
        - 🏀 (basketball) - values 1-5 (4-5 = score)
        - ⚽ (football/soccer) - values 1-5 (4-5 = goal)
        - 🎳 (bowling) - values 1-6 (6 = strike)
        - 🎰 (slot machine) - values 1-64 (64 = jackpot 777)

        Args:
            peer: Target chat/user
            emoji: One of the supported game emoji
            reply_to_msg_id: Message ID to reply to
            silent: Send without notification
            timeout: Request timeout

        Returns:
            Updates with the sent message. The dice value is in
            message.media.value after the animation completes.
        """
        from telecraft.tl.generated.types import (
            InputMediaDice,
            InputReplyToMessage,
        )

        SUPPORTED_DICE = {"🎲", "🎯", "🏀", "⚽", "🎳", "🎰"}
        if emoji not in SUPPORTED_DICE:
            raise MtprotoClientError(
                f"send_dice: unsupported emoji '{emoji}'. "
                f"Supported: {', '.join(SUPPORTED_DICE)}"
            )

        p = await self.resolve_peer(peer, timeout=timeout)
        try:
            input_peer = self.entities.input_peer(p)
        except EntityCacheError:
            await self._prime_entities_for_reply(want=p, timeout=timeout)
            input_peer = self.entities.input_peer(p)

        media = InputMediaDice(emoticon=emoji)

        msg_flags = 0
        if silent:
            msg_flags |= 32
        if reply_to_msg_id is not None:
            msg_flags |= 1

        reply_to = None
        if reply_to_msg_id is not None:
            reply_to = InputReplyToMessage(
                flags=0,
                reply_to_msg_id=reply_to_msg_id,
                top_msg_id=None,
                reply_to_peer_id=None,
                quote_text=None,
                quote_entities=None,
                quote_offset=None,
            )

        import random

        res = await self.invoke_api(
            MessagesSendMedia(
                flags=msg_flags,
                silent=silent if silent else None,
                background=None,
                clear_draft=None,
                noforwards=None,
                update_stickersets_order=None,
                invert_media=None,
                allow_paid_floodskip=None,
                peer=input_peer,
                reply_to=reply_to,
                media=media,
                message="",
                random_id=random.randint(1, 2**63 - 1),
                reply_markup=None,
                entities=None,
                schedule_date=None,
                schedule_repeat_period=None,
                send_as=None,
                quick_reply_shortcut=None,
                effect=None,
                allow_paid_stars=None,
                suggested_post=None,
            ),
            timeout=timeout,
        )
        self._ingest_from_updates_result(res)
        return res

    async def roll_dice(
        self,
        peer: PeerRef,
        *,
        reply_to_msg_id: int | None = None,
        silent: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        """Shortcut for send_dice with 🎲 emoji."""
        return await self.send_dice(
            peer, "🎲", reply_to_msg_id=reply_to_msg_id, silent=silent, timeout=timeout
        )

    async def throw_darts(
        self,
        peer: PeerRef,
        *,
        reply_to_msg_id: int | None = None,
        silent: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        """Shortcut for send_dice with 🎯 emoji (darts)."""
        return await self.send_dice(
            peer, "🎯", reply_to_msg_id=reply_to_msg_id, silent=silent, timeout=timeout
        )

    async def shoot_basketball(
        self,
        peer: PeerRef,
        *,
        reply_to_msg_id: int | None = None,
        silent: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        """Shortcut for send_dice with 🏀 emoji (basketball)."""
        return await self.send_dice(
            peer, "🏀", reply_to_msg_id=reply_to_msg_id, silent=silent, timeout=timeout
        )

    async def kick_football(
        self,
        peer: PeerRef,
        *,
        reply_to_msg_id: int | None = None,
        silent: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        """Shortcut for send_dice with ⚽ emoji (football/soccer)."""
        return await self.send_dice(
            peer, "⚽", reply_to_msg_id=reply_to_msg_id, silent=silent, timeout=timeout
        )

    async def roll_bowling(
        self,
        peer: PeerRef,
        *,
        reply_to_msg_id: int | None = None,
        silent: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        """Shortcut for send_dice with 🎳 emoji (bowling)."""
        return await self.send_dice(
            peer, "🎳", reply_to_msg_id=reply_to_msg_id, silent=silent, timeout=timeout
        )

    async def spin_slot_machine(
        self,
        peer: PeerRef,
        *,
        reply_to_msg_id: int | None = None,
        silent: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        """Shortcut for send_dice with 🎰 emoji (slot machine)."""
        return await self.send_dice(
            peer, "🎰", reply_to_msg_id=reply_to_msg_id, silent=silent, timeout=timeout
        )

    # ========================== Voice & Video Notes ==========================

    async def send_voice(
        self,
        peer: PeerRef,
        path: str | Path,
        *,
        duration: int | None = None,
        waveform: bytes | None = None,
        caption: str | None = None,
        reply_to_msg_id: int | None = None,
        silent: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        """
        Send a voice message (.ogg OPUS format).

        Args:
            peer: Target chat/user
            path: Path to the audio file (should be .ogg with OPUS codec)
            duration: Duration in seconds (auto-detected if None)
            waveform: Waveform data for visualization (optional)
            caption: Caption text
            reply_to_msg_id: Message ID to reply to
            silent: Send without notification
        """
        from pathlib import Path as PathlibPath
        from secrets import randbits

        from telecraft.client.media import upload_file
        from telecraft.tl.generated.types import (
            DocumentAttributeAudio,
            DocumentAttributeFilename,
            InputMediaUploadedDocument,
            InputReplyToMessage,
        )

        if not self.is_connected:
            raise MtprotoClientError("Not connected")

        p = PathlibPath(path)
        if not p.exists() or not p.is_file():
            raise MtprotoClientError(f"send_voice: not a file: {p}")

        input_file = await upload_file(
            p,
            invoke_api=self.invoke_api,
            timeout=timeout,
        )

        # Voice message attributes
        audio_flags = 1024  # voice flag (bit 10)
        if waveform is not None:
            audio_flags |= 4

        attrs = [
            DocumentAttributeAudio(
                flags=audio_flags,
                voice=True,
                duration=duration or 0,
                title=None,
                performer=None,
                waveform=waveform,
            ),
            DocumentAttributeFilename(file_name=p.name),
        ]

        media = InputMediaUploadedDocument(
            flags=0,
            nosound_video=False,
            force_file=False,
            spoiler=False,
            file=input_file,
            thumb=None,
            mime_type="audio/ogg",
            attributes=attrs,
            stickers=None,
            video_cover=None,
            video_timestamp=None,
            ttl_seconds=None,
        )

        reply_to = None
        if reply_to_msg_id is not None:
            reply_to = InputReplyToMessage(
                flags=0,
                reply_to_msg_id=int(reply_to_msg_id),
                top_msg_id=None,
                reply_to_peer_id=None,
                quote_text=None,
                quote_entities=None,
                quote_offset=None,
            )

        p2 = await self.resolve_peer(peer, timeout=timeout)
        try:
            input_peer = self.entities.input_peer(p2)
        except EntityCacheError:
            await self._prime_entities_for_reply(want=p2, timeout=timeout)
            input_peer = self.entities.input_peer(p2)

        res = await self.invoke_api(
            MessagesSendMedia(
                flags=0,
                silent=bool(silent),
                background=False,
                clear_draft=False,
                noforwards=False,
                update_stickersets_order=False,
                invert_media=False,
                allow_paid_floodskip=False,
                peer=input_peer,
                reply_to=reply_to,
                media=media,
                message=caption or "",
                random_id=randbits(63),
                reply_markup=None,
                entities=None,
                schedule_date=None,
                schedule_repeat_period=None,
                send_as=None,
                quick_reply_shortcut=None,
                effect=None,
                allow_paid_stars=None,
                suggested_post=None,
            ),
            timeout=timeout,
        )
        self._ingest_from_updates_result(res)
        return res

    async def send_video_note(
        self,
        peer: PeerRef,
        path: str | Path,
        *,
        duration: int | None = None,
        length: int = 240,
        caption: str | None = None,
        reply_to_msg_id: int | None = None,
        silent: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        """
        Send a round video note (circular video message).

        Args:
            peer: Target chat/user
            path: Path to the video file (should be square, ideally 240x240)
            duration: Duration in seconds
            length: Video dimensions (should be square, default 240)
            caption: Caption text
            reply_to_msg_id: Message ID to reply to
            silent: Send without notification
        """
        from pathlib import Path as PathlibPath
        from secrets import randbits

        from telecraft.client.media import upload_file
        from telecraft.tl.generated.types import (
            DocumentAttributeFilename,
            DocumentAttributeVideo,
            InputMediaUploadedDocument,
            InputReplyToMessage,
        )

        if not self.is_connected:
            raise MtprotoClientError("Not connected")

        p = PathlibPath(path)
        if not p.exists() or not p.is_file():
            raise MtprotoClientError(f"send_video_note: not a file: {p}")

        input_file = await upload_file(
            p,
            invoke_api=self.invoke_api,
            timeout=timeout,
        )

        # Video note attributes (round_message = True)
        video_flags = 1  # round_message flag (bit 0)
        if True:  # supports_streaming
            video_flags |= 2

        attrs = [
            DocumentAttributeVideo(
                flags=video_flags,
                round_message=True,
                supports_streaming=True,
                nosound=None,
                duration=float(duration or 0),
                w=length,
                h=length,
                preload_prefix_size=None,
                video_start_ts=None,
                video_codec=None,
            ),
            DocumentAttributeFilename(file_name=p.name),
        ]

        media = InputMediaUploadedDocument(
            flags=0,
            nosound_video=False,
            force_file=False,
            spoiler=False,
            file=input_file,
            thumb=None,
            mime_type="video/mp4",
            attributes=attrs,
            stickers=None,
            video_cover=None,
            video_timestamp=None,
            ttl_seconds=None,
        )

        reply_to = None
        if reply_to_msg_id is not None:
            reply_to = InputReplyToMessage(
                flags=0,
                reply_to_msg_id=int(reply_to_msg_id),
                top_msg_id=None,
                reply_to_peer_id=None,
                quote_text=None,
                quote_entities=None,
                quote_offset=None,
            )

        p2 = await self.resolve_peer(peer, timeout=timeout)
        try:
            input_peer = self.entities.input_peer(p2)
        except EntityCacheError:
            await self._prime_entities_for_reply(want=p2, timeout=timeout)
            input_peer = self.entities.input_peer(p2)

        res = await self.invoke_api(
            MessagesSendMedia(
                flags=0,
                silent=bool(silent),
                background=False,
                clear_draft=False,
                noforwards=False,
                update_stickersets_order=False,
                invert_media=False,
                allow_paid_floodskip=False,
                peer=input_peer,
                reply_to=reply_to,
                media=media,
                message=caption or "",
                random_id=randbits(63),
                reply_markup=None,
                entities=None,
                schedule_date=None,
                schedule_repeat_period=None,
                send_as=None,
                quick_reply_shortcut=None,
                effect=None,
                allow_paid_stars=None,
                suggested_post=None,
            ),
            timeout=timeout,
        )
        self._ingest_from_updates_result(res)
        return res

    # ========================== Polls & Quizzes ==========================

    async def send_poll(
        self,
        peer: PeerRef,
        question: str,
        options: list[str],
        *,
        multiple_choice: bool = False,
        public_voters: bool = False,
        close_period: int | None = None,
        close_date: int | None = None,
        reply_to_msg_id: int | None = None,
        silent: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        """
        Send a poll.

        Args:
            peer: The chat to send the poll to
            question: The poll question
            options: List of answer options (2-10 options)
            multiple_choice: Allow multiple answers
            public_voters: Show who voted
            close_period: Auto-close after X seconds
            close_date: Auto-close at Unix timestamp
            reply_to_msg_id: Reply to specific message
            silent: Send without notification
            timeout: RPC timeout in seconds

        Returns:
            Updates object with the sent message
        """
        from telecraft.tl.generated.types import (
            InputMediaPoll,
            Poll,
            PollAnswer,
            TextWithEntities,
        )

        if len(options) < 2:
            raise MtprotoClientError("send_poll: need at least 2 options")
        if len(options) > 10:
            raise MtprotoClientError("send_poll: maximum 10 options")

        p = await self.resolve_peer(peer, timeout=timeout)

        try:
            input_peer = self.entities.input_peer(p)
        except EntityCacheError:
            await self._prime_entities_for_reply(want=p, timeout=timeout)
            input_peer = self.entities.input_peer(p)

        # Build poll answers
        answers = []
        for i, opt in enumerate(options):
            answers.append(
                PollAnswer(
                    text=TextWithEntities(text=opt, entities=[]),
                    option=bytes([i]),  # option identifier
                )
            )

        # Build poll flags
        poll_flags = 0
        if public_voters:
            poll_flags |= 2  # flags.1
        if multiple_choice:
            poll_flags |= 4  # flags.2
        if close_period is not None:
            poll_flags |= 16  # flags.4
        if close_date is not None:
            poll_flags |= 32  # flags.5

        import random
        poll = Poll(
            id=random.randint(1, 2**63 - 1),
            flags=poll_flags,
            closed=None,
            public_voters=public_voters if public_voters else None,
            multiple_choice=multiple_choice if multiple_choice else None,
            quiz=None,
            question=TextWithEntities(text=question, entities=[]),
            answers=answers,
            close_period=close_period,
            close_date=close_date,
        )

        media = InputMediaPoll(
            flags=0,
            poll=poll,
            correct_answers=None,
            solution=None,
            solution_entities=None,
        )

        # Build message flags
        msg_flags = 0
        if silent:
            msg_flags |= 32  # flags.5
        if reply_to_msg_id is not None:
            msg_flags |= 1  # flags.0

        from telecraft.tl.generated.types import InputReplyToMessage

        reply_to = None
        if reply_to_msg_id is not None:
            reply_to = InputReplyToMessage(
                flags=0,
                reply_to_msg_id=reply_to_msg_id,
                top_msg_id=None,
                reply_to_peer_id=None,
                quote_text=None,
                quote_entities=None,
                quote_offset=None,
            )

        res = await self.invoke_api(
            MessagesSendMedia(
                flags=msg_flags,
                silent=silent if silent else None,
                background=None,
                clear_draft=None,
                noforwards=None,
                update_stickersets_order=None,
                invert_media=None,
                allow_paid_floodskip=None,
                peer=input_peer,
                reply_to=reply_to,
                media=media,
                message="",
                random_id=random.randint(1, 2**63 - 1),
                reply_markup=None,
                entities=None,
                schedule_date=None,
                schedule_repeat_period=None,
                send_as=None,
                quick_reply_shortcut=None,
                effect=None,
                allow_paid_stars=None,
                suggested_post=None,
            ),
            timeout=timeout,
        )

        self._ingest_from_updates_result(res)
        return res

    async def send_quiz(
        self,
        peer: PeerRef,
        question: str,
        options: list[str],
        correct_option: int,
        *,
        explanation: str | None = None,
        public_voters: bool = False,
        close_period: int | None = None,
        reply_to_msg_id: int | None = None,
        silent: bool = False,
        timeout: float = 20.0,
    ) -> Any:
        """
        Send a quiz (poll with correct answer).

        Args:
            peer: The chat to send the quiz to
            question: The quiz question
            options: List of answer options
            correct_option: Index of the correct answer (0-based)
            explanation: Explanation shown after answering
            public_voters: Show who voted
            close_period: Auto-close after X seconds
            reply_to_msg_id: Reply to specific message
            silent: Send without notification
            timeout: RPC timeout in seconds

        Returns:
            Updates object with the sent message
        """
        from telecraft.tl.generated.types import (
            InputMediaPoll,
            Poll,
            PollAnswer,
            TextWithEntities,
        )

        if len(options) < 2:
            raise MtprotoClientError("send_quiz: need at least 2 options")
        if len(options) > 10:
            raise MtprotoClientError("send_quiz: maximum 10 options")
        if correct_option < 0 or correct_option >= len(options):
            raise MtprotoClientError(f"send_quiz: correct_option must be 0-{len(options)-1}")

        p = await self.resolve_peer(peer, timeout=timeout)

        try:
            input_peer = self.entities.input_peer(p)
        except EntityCacheError:
            await self._prime_entities_for_reply(want=p, timeout=timeout)
            input_peer = self.entities.input_peer(p)

        # Build poll answers
        answers = []
        for i, opt in enumerate(options):
            answers.append(
                PollAnswer(
                    text=TextWithEntities(text=opt, entities=[]),
                    option=bytes([i]),
                )
            )

        # Build poll flags (quiz mode)
        poll_flags = 8  # flags.3 = quiz
        if public_voters:
            poll_flags |= 2  # flags.1
        if close_period is not None:
            poll_flags |= 16  # flags.4

        import random
        poll = Poll(
            id=random.randint(1, 2**63 - 1),
            flags=poll_flags,
            closed=None,
            public_voters=public_voters if public_voters else None,
            multiple_choice=None,
            quiz=True,
            question=TextWithEntities(text=question, entities=[]),
            answers=answers,
            close_period=close_period,
            close_date=None,
        )

        # Build media flags
        media_flags = 1  # flags.0 = correct_answers
        if explanation:
            media_flags |= 2  # flags.1 = solution

        media = InputMediaPoll(
            flags=media_flags,
            poll=poll,
            correct_answers=[bytes([correct_option])],
            solution=explanation,
            solution_entities=[] if explanation else None,
        )

        # Build message flags
        msg_flags = 0
        if silent:
            msg_flags |= 32
        if reply_to_msg_id is not None:
            msg_flags |= 1

        from telecraft.tl.generated.types import InputReplyToMessage

        reply_to = None
        if reply_to_msg_id is not None:
            reply_to = InputReplyToMessage(
                flags=0,
                reply_to_msg_id=reply_to_msg_id,
                top_msg_id=None,
                reply_to_peer_id=None,
                quote_text=None,
                quote_entities=None,
                quote_offset=None,
            )

        res = await self.invoke_api(
            MessagesSendMedia(
                flags=msg_flags,
                silent=silent if silent else None,
                background=None,
                clear_draft=None,
                noforwards=None,
                update_stickersets_order=None,
                invert_media=None,
                allow_paid_floodskip=None,
                peer=input_peer,
                reply_to=reply_to,
                media=media,
                message="",
                random_id=random.randint(1, 2**63 - 1),
                reply_markup=None,
                entities=None,
                schedule_date=None,
                schedule_repeat_period=None,
                send_as=None,
                quick_reply_shortcut=None,
                effect=None,
                allow_paid_stars=None,
                suggested_post=None,
            ),
            timeout=timeout,
        )

        self._ingest_from_updates_result(res)
        return res

    async def vote_poll(
        self,
        peer: PeerRef,
        msg_id: int,
        options: int | list[int],
        *,
        timeout: float = 20.0,
    ) -> Any:
        """
        Vote on a poll.

        Args:
            peer: The chat containing the poll
            msg_id: Message ID of the poll
            options: Option index(es) to vote for (0-based)
            timeout: RPC timeout in seconds

        Returns:
            Updates object
        """
        p = await self.resolve_peer(peer, timeout=timeout)

        try:
            input_peer = self.entities.input_peer(p)
        except EntityCacheError:
            await self._prime_entities_for_reply(want=p, timeout=timeout)
            input_peer = self.entities.input_peer(p)

        # Convert option indices to bytes
        if isinstance(options, int):
            option_bytes = [bytes([options])]
        else:
            option_bytes = [bytes([opt]) for opt in options]

        return await self.invoke_api(
            MessagesSendVote(peer=input_peer, msg_id=msg_id, options=option_bytes),
            timeout=timeout,
        )

    async def close_poll(
        self,
        peer: PeerRef,
        msg_id: int,
        *,
        timeout: float = 20.0,
    ) -> Any:
        """
        Close a poll (stop accepting votes).

        Args:
            peer: The chat containing the poll
            msg_id: Message ID of the poll
            timeout: RPC timeout in seconds

        Returns:
            Updates object
        """
        # To close a poll, we edit the message with closed=True
        # This requires getting the current poll first, then editing it
        from telecraft.tl.generated.types import InputMediaPoll

        p = await self.resolve_peer(peer, timeout=timeout)

        try:
            input_peer = self.entities.input_peer(p)
        except EntityCacheError:
            await self._prime_entities_for_reply(want=p, timeout=timeout)
            input_peer = self.entities.input_peer(p)

        from telecraft.tl.generated.functions import MessagesEditMessage

        # Edit the message with a closed poll media
        # We need to get the original poll first
        # For simplicity, we'll use the edit approach with minimal poll
        res = await self.invoke_api(
            MessagesEditMessage(
                flags=16384,  # flags.14 = media
                no_webpage=None,
                invert_media=None,
                peer=input_peer,
                id=msg_id,
                message=None,
                media=InputMediaPoll(
                    flags=0,
                    poll=None,  # Will close the existing poll
                    correct_answers=None,
                    solution=None,
                    solution_entities=None,
                ),
                reply_markup=None,
                entities=None,
                schedule_date=None,
                quick_reply_shortcut_id=None,
            ),
            timeout=timeout,
        )

        self._ingest_from_updates_result(res)
        return res

    async def get_poll_results(
        self,
        peer: PeerRef,
        msg_id: int,
        *,
        timeout: float = 20.0,
    ) -> Any:
        """
        Get poll results/votes.

        Args:
            peer: The chat containing the poll
            msg_id: Message ID of the poll
            timeout: RPC timeout in seconds

        Returns:
            Updates object with poll results
        """
        p = await self.resolve_peer(peer, timeout=timeout)

        try:
            input_peer = self.entities.input_peer(p)
        except EntityCacheError:
            await self._prime_entities_for_reply(want=p, timeout=timeout)
            input_peer = self.entities.input_peer(p)

        return await self.invoke_api(
            MessagesGetPollResults(peer=input_peer, msg_id=msg_id),
            timeout=timeout,
        )

    async def add_user_to_group(
        self,
        group: PeerRef,
        user: PeerRef,
        *,
        fwd_limit: int = 10,
        timeout: float = 20.0,
    ) -> Any:
        """
        Add a user to a group.

        - basic groups (peer_type='chat'): messages.addChatUser(chat_id, user_id, fwd_limit)
        - supergroups/channels (peer_type='channel'): channels.inviteToChannel(channel, users=[user])
        """
        g = await self.resolve_peer(group, timeout=timeout)
        u = await self.resolve_peer(user, timeout=timeout)
        if u.peer_type != "user":
            raise MtprotoClientError(f"add_user_to_group: user must be a user, got {u.peer_type}")

        async def _build_input_user() -> InputUser:
            try:
                return self.entities.input_user(int(u.peer_id))
            except EntityCacheError:
                await self._prime_entities_for_reply(want=Peer.user(int(u.peer_id)), timeout=timeout)
                return self.entities.input_user(int(u.peer_id))

        async def _refresh_user_ref() -> None:
            """
            Best-effort refresh when Telegram returns USER_ID_INVALID/USER_INVALID.

            Common case: stale username/phone -> user_id mapping in the persisted EntityCache.
            """
            nonlocal u
            # If we have a username/phone ref, force a network resolve to refresh user_id/access_hash.
            if isinstance(user, str) and user.strip():
                try:
                    parsed = parse_peer_ref(user.strip())
                except Exception:
                    parsed = user.strip()
                if isinstance(parsed, str):
                    if parsed.startswith("@"):
                        u = await self.resolve_username(parsed, timeout=timeout, force=True)
                        return
                    if parsed.startswith("+"):
                        u = await self.resolve_phone(parsed, timeout=timeout, force=True)
                        return
            # Otherwise, just try priming (may refresh access_hash if the user is present in dialogs).
            await self._prime_entities_for_reply(want=Peer.user(int(u.peer_id)), timeout=timeout)

        input_user = await _build_input_user()

        if g.peer_type == "chat":
            try:
                res = await self.invoke_api(
                    MessagesAddChatUser(
                        chat_id=int(g.peer_id),
                        user_id=input_user,
                        fwd_limit=int(fwd_limit),
                    ),
                    timeout=timeout,
                )
            except RpcErrorException as e:
                if e.message in {"USER_ID_INVALID", "USER_INVALID"}:
                    await _refresh_user_ref()
                    input_user = await _build_input_user()
                    res = await self.invoke_api(
                        MessagesAddChatUser(
                            chat_id=int(g.peer_id),
                            user_id=input_user,
                            fwd_limit=int(fwd_limit),
                        ),
                        timeout=timeout,
                    )
                else:
                    raise
            self._ingest_from_updates_result(res)
            return res

        if g.peer_type == "channel":
            try:
                input_channel = self.entities.input_channel(int(g.peer_id))
            except EntityCacheError:
                await self._prime_entities_for_reply(want=Peer.channel(int(g.peer_id)), timeout=timeout)
                input_channel = self.entities.input_channel(int(g.peer_id))
            try:
                res = await self.invoke_api(
                    ChannelsInviteToChannel(channel=input_channel, users=[input_user]),
                    timeout=timeout,
                )
            except RpcErrorException as e:
                if e.message in {"USER_ID_INVALID", "USER_INVALID"}:
                    await _refresh_user_ref()
                    input_user = await _build_input_user()
                    res = await self.invoke_api(
                        ChannelsInviteToChannel(channel=input_channel, users=[input_user]),
                        timeout=timeout,
                    )
                else:
                    raise
            self._ingest_from_updates_result(res)
            return res

        raise MtprotoClientError(f"add_user_to_group: unsupported peer_type={g.peer_type!r}")

    async def add_users_to_group(
        self,
        group: PeerRef,
        users: list[PeerRef],
        *,
        timeout: float = 20.0,
        on_error: str = "skip",  # "skip", "raise", "collect"
    ) -> dict[str, Any]:
        """
        Add multiple users to a group/channel.

        Args:
            group: The group/channel to add users to
            users: List of users to add
            timeout: RPC timeout per user
            on_error: How to handle errors:
                - "skip": Skip failed users and continue
                - "raise": Raise on first error
                - "collect": Collect all errors and return them

        Returns:
            Dict with:
                - "success": list of successfully added user IDs
                - "failed": list of (user_id, error_message) tuples
                - "total": total attempted
        """
        success: list[int] = []
        failed: list[tuple[int, str]] = []

        for user_ref in users:
            try:
                u = await self.resolve_peer(user_ref, timeout=timeout)
                await self.add_user_to_group(group, user_ref, timeout=timeout)
                success.append(int(u.peer_id))
            except Exception as e:
                user_id = 0
                try:
                    u = await self.resolve_peer(user_ref, timeout=timeout)
                    user_id = int(u.peer_id)
                except Exception:
                    pass
                
                error_msg = str(e)
                if on_error == "raise":
                    raise
                failed.append((user_id, error_msg))

        return {
            "success": success,
            "failed": failed,
            "total": len(users),
        }

    async def get_group_members(
        self,
        group: PeerRef,
        *,
        limit: int | None = None,
        timeout: float = 20.0,
    ) -> list[Any]:
        """
        Get all members of a group/channel.

        This is a convenience wrapper around iter_participants that returns a list.

        Args:
            group: The group/channel to get members from
            limit: Maximum number of members to return (None = all)
            timeout: RPC timeout

        Returns:
            List of User objects
        """
        members: list[Any] = []
        async for member in self.iter_participants(group, limit=limit, timeout=timeout):
            members.append(member)
        return members

    async def transfer_members(
        self,
        from_group: PeerRef,
        to_group: PeerRef,
        *,
        limit: int | None = None,
        exclude_bots: bool = True,
        exclude_admins: bool = False,
        timeout: float = 20.0,
        on_error: str = "skip",
    ) -> dict[str, Any]:
        """
        Transfer members from one group to another.

        IMPORTANT: You need:
        - Admin access to see members in from_group (or group allows member viewing)
        - Invite permission in to_group

        Args:
            from_group: Source group to get members from
            to_group: Target group to add members to
            limit: Maximum number of members to transfer
            exclude_bots: Skip bots (default True)
            exclude_admins: Skip admins (default False)
            timeout: RPC timeout per operation
            on_error: How to handle errors ("skip", "raise", "collect")

        Returns:
            Dict with transfer statistics
        """
        # Get members from source group
        members = await self.get_group_members(from_group, limit=limit, timeout=timeout)

        # Filter members
        users_to_add: list[tuple[str, int]] = []
        skipped: list[tuple[int, str]] = []

        for member in members:
            user_id = getattr(member, "id", None)
            if not user_id:
                continue

            # Check if bot
            is_bot = getattr(member, "bot", False)
            if exclude_bots and is_bot:
                skipped.append((user_id, "bot"))
                continue

            # Check if self
            if user_id == self.self_user_id:
                skipped.append((user_id, "self"))
                continue

            users_to_add.append(("user", user_id))

        # Add members to target group
        result = await self.add_users_to_group(
            to_group,
            users_to_add,  # type: ignore
            timeout=timeout,
            on_error=on_error,
        )

        result["skipped"] = skipped
        result["source_total"] = len(members)

        return result

    async def remove_user_from_group(
        self,
        group: PeerRef,
        user: PeerRef,
        *,
        timeout: float = 20.0,
    ) -> Any:
        """
        Remove a user from a group/channel (kick without ban).

        This is an alias for kick_user for groups.

        Args:
            group: The group/channel to remove from
            user: The user to remove
            timeout: RPC timeout

        Returns:
            Updates object
        """
        g = await self.resolve_peer(group, timeout=timeout)

        if g.peer_type == "chat":
            # For basic groups, use messages.deleteChatUser
            u = await self.resolve_peer(user, timeout=timeout)
            if u.peer_type != "user":
                raise MtprotoClientError(f"remove_user_from_group: user must be a user, got {u.peer_type}")

            try:
                input_user = self.entities.input_user(int(u.peer_id))
            except EntityCacheError:
                await self._prime_entities_for_reply(want=Peer.user(int(u.peer_id)), timeout=timeout)
                input_user = self.entities.input_user(int(u.peer_id))

            from telecraft.tl.generated.functions import MessagesDeleteChatUser

            res = await self.invoke_api(
                MessagesDeleteChatUser(flags=0, revoke_history=False, chat_id=int(g.peer_id), user_id=input_user),
                timeout=timeout,
            )
            self._ingest_from_updates_result(res)
            return res

        elif g.peer_type == "channel":
            # For channels/supergroups, use kick_user (ban + unban)
            return await self.kick_user(group, user, timeout=timeout)

        raise MtprotoClientError(f"remove_user_from_group: unsupported peer_type={g.peer_type!r}")

    def _ingest_from_updates_result(self, obj: Any) -> None:
        """
        Best-effort: many API methods (sendMessage/sendMedia, etc.) return Updates-like objects
        that carry `users`/`chats`. Ingest them to keep access_hash cache fresh.
        """
        try:
            users = cast(list[Any], getattr(obj, "users", []))
            chats = cast(list[Any], getattr(obj, "chats", []))
            if users:
                self.entities.ingest_users(list(users))
            if chats:
                self.entities.ingest_chats(list(chats))
            if users or chats:
                self._persist_entities_cache()
        except Exception:
            return

    async def _prime_entities_for_reply(
        self,
        *,
        want: Peer | None = None,
        limit: int = 100,
        timeout: float = 20.0,
    ) -> None:
        """
        Best-effort priming used by reply/send guardrails.

        - rate-limited by a small cooldown
        - serialized by a lock to avoid concurrent dialog fetches
        - optionally stops early if the wanted peer becomes resolvable
        """
        # Cooldown: avoid spamming dialogs under bursty short updates.
        now = time.monotonic()
        if (now - self._prime_last_attempt) < 3.0:
            return
        async with self._prime_lock:
            now2 = time.monotonic()
            if (now2 - self._prime_last_attempt) < 3.0:
                return
            self._prime_last_attempt = now2

            # Small, then bigger if we still can't build the peer.
            # Note: archived chats live under folder_id=1 and won't be returned by default.
            await self.prime_entities(limit=int(limit), folder_id=None, timeout=timeout)
            if want is None:
                return
            try:
                _ = self.entities.input_peer(want)
                return
            except EntityCacheError:
                pass
            # Try archived folder (folder_id=1) before increasing limits.
            if want.peer_type == "channel":
                await self.prime_entities(limit=int(limit), folder_id=1, timeout=timeout)
                try:
                    _ = self.entities.input_peer(want)
                    return
                except EntityCacheError:
                    pass
            if int(limit) < 300:
                await self.prime_entities(limit=300, folder_id=None, timeout=timeout)
                if want.peer_type == "channel":
                    try:
                        _ = self.entities.input_peer(want)
                        return
                    except EntityCacheError:
                        await self.prime_entities(limit=300, folder_id=1, timeout=timeout)
            return

    async def _client_for_dc(self, dc_id: int, *, timeout: float = 20.0) -> MtprotoClient:
        """
        Best-effort cross-DC helper for media downloads:
        - connect to dc_id
        - import authorization using auth.exportAuthorization/auth.importAuthorization
        """
        if int(dc_id) == int(self._dc_id):
            return self
        existing = self._media_clients.get(int(dc_id))
        if existing is not None and existing.is_connected:
            return existing

        if self._init is None:
            raise MtprotoClientError("ClientInit(api_id=...) is required for cross-DC operations")

        c = MtprotoClient(network=self._network, dc_id=int(dc_id), init=self._init, session_path=None)
        await c.connect(timeout=timeout)
        exported = await self.invoke_api(AuthExportAuthorization(dc_id=int(dc_id)), timeout=timeout)
        exp_id = getattr(exported, "id", None)
        exp_bytes = getattr(exported, "bytes", None)
        if not isinstance(exp_id, int) or not isinstance(exp_bytes, (bytes, bytearray)):
            raise MtprotoClientError(
                f"Unexpected auth.exportAuthorization result: {type(exported).__name__}"
            )
        await c.invoke_api(AuthImportAuthorization(id=int(exp_id), bytes=bytes(exp_bytes)), timeout=timeout)
        self._media_clients[int(dc_id)] = c
        return c

    async def download_media(
        self,
        message_or_event: Any,
        *,
        dest: str | Path | None = None,
        timeout: float = 20.0,
    ) -> Path | bytes | None:
        """
        Media MVP: download photo/document from a TL message or MessageEvent.

        Args:
            message_or_event: TL message object or MessageEvent with media
            dest: Optional destination path (file or directory). If None, returns bytes.
            timeout: RPC timeout in seconds

        Returns:
            - bytes if dest is None
            - Path to saved file if dest is provided
            - None if no media found
        """
        from telecraft.client.media import (
            ExtractedMediaWithCache,
            MediaError,
            download_via_get_file,
            ensure_dest_path,
            extract_media,
        )

        m = extract_media(message_or_event)
        if m is None:
            return None

        # Check for cached bytes (small photos are sometimes embedded)
        if isinstance(m, ExtractedMediaWithCache) and m.cached_bytes:
            data = m.cached_bytes
        else:
            try:
                c = await self._client_for_dc(int(m.dc_id), timeout=timeout)
                data = await download_via_get_file(
                    invoke_api=c.invoke_api,
                    location=m.location,
                    timeout=timeout,
                    expected_size=m.size,
                )
            except MediaError as e:
                raise MtprotoClientError(str(e)) from e

        if dest is None:
            return data

        out_path = ensure_dest_path(dest, file_name=m.file_name)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(data)
        return out_path

    async def iter_dialogs(
        self,
        *,
        limit: int | None = None,
        folder_id: int | None = None,
        timeout: float = 20.0,
    ) -> AsyncIterator[Any]:
        """
        Async generator that iterates over all dialogs with pagination.

        Args:
            limit: Maximum number of dialogs to return (None for all)
            folder_id: Folder ID (None for main list, 1 for archived)
            timeout: RPC timeout in seconds

        Yields:
            Dialog TL objects
        """
        from telecraft.tl.generated.functions import MessagesGetDialogs
        from telecraft.tl.generated.types import (
            InputPeerEmpty,
            MessagesDialogs,
            MessagesDialogsSlice,
            MessagesDialogsNotModified,
        )

        offset_date = 0
        offset_id = 0
        offset_peer: Any = InputPeerEmpty()
        total_yielded = 0
        batch_size = 100  # Telegram's typical max per request

        while True:
            remaining = None
            if limit is not None:
                remaining = limit - total_yielded
                if remaining <= 0:
                    break
                batch_limit = min(batch_size, remaining)
            else:
                batch_limit = batch_size

            res = await self.invoke_api(
                MessagesGetDialogs(
                    flags=0,
                    exclude_pinned=False,
                    folder_id=int(folder_id) if folder_id is not None else None,
                    offset_date=offset_date,
                    offset_id=offset_id,
                    offset_peer=offset_peer,
                    limit=batch_limit,
                    hash=0,
                ),
                timeout=timeout,
            )

            if isinstance(res, MessagesDialogsNotModified):
                # No changes since last fetch
                break

            if not isinstance(res, (MessagesDialogs, MessagesDialogsSlice)):
                break

            # Ingest entities for later use
            users = cast(list[Any], getattr(res, "users", []))
            chats = cast(list[Any], getattr(res, "chats", []))
            self.entities.ingest_users(list(users))
            self.entities.ingest_chats(list(chats))

            dialogs = cast(list[Any], getattr(res, "dialogs", []))
            messages = cast(list[Any], getattr(res, "messages", []))

            if not dialogs:
                break

            for d in dialogs:
                if limit is not None and total_yielded >= limit:
                    return
                yield d
                total_yielded += 1

            # MessagesDialogs (not slice) means we got all dialogs
            if isinstance(res, MessagesDialogs):
                break

            # For MessagesDialogsSlice, prepare pagination
            # Find the last dialog's message for offset
            if messages:
                last_msg = messages[-1]
                offset_date = int(getattr(last_msg, "date", 0) or 0)
                offset_id = int(getattr(last_msg, "id", 0) or 0)
                # Get the peer from the last dialog
                last_dialog_peer = getattr(dialogs[-1], "peer", None)
                if last_dialog_peer is not None:
                    # Try to convert peer to input_peer
                    try:
                        from telecraft.client.peers import Peer
                        p = Peer.from_tl(last_dialog_peer)
                        offset_peer = self.entities.input_peer(p)
                    except Exception:  # noqa: BLE001
                        # Continue with empty peer
                        pass
            else:
                # No messages to paginate with
                break

            # Safety check: if we got fewer dialogs than requested, we're done
            if len(dialogs) < batch_limit:
                break

        # Persist entities after iteration
        self._persist_entities_cache(force=True)

    async def iter_messages(
        self,
        peer: PeerRef,
        *,
        limit: int | None = None,
        offset_id: int = 0,
        min_id: int = 0,
        max_id: int = 0,
        timeout: float = 20.0,
    ) -> AsyncIterator[Any]:
        """
        Async generator that iterates over messages in a chat with pagination.

        Args:
            peer: The chat/channel to get messages from
            limit: Maximum number of messages to return (None for all)
            offset_id: Start from this message ID (0 for latest)
            min_id: Minimum message ID to return
            max_id: Maximum message ID to return
            timeout: RPC timeout in seconds

        Yields:
            Message TL objects (newest first by default)
        """
        from telecraft.tl.generated.types import (
            MessagesChannelMessages,
            MessagesMessages,
            MessagesMessagesSlice,
        )

        p = await self.resolve_peer(peer, timeout=timeout)
        try:
            input_peer = self.entities.input_peer(p)
        except EntityCacheError:
            await self._prime_entities_for_reply(want=p, timeout=timeout)
            input_peer = self.entities.input_peer(p)

        total_yielded = 0
        current_offset_id = offset_id
        batch_size = 100  # Telegram's typical max per request

        while True:
            remaining = None
            if limit is not None:
                remaining = limit - total_yielded
                if remaining <= 0:
                    break
                batch_limit = min(batch_size, remaining)
            else:
                batch_limit = batch_size

            res = await self.invoke_api(
                MessagesGetHistory(
                    peer=input_peer,
                    offset_id=current_offset_id,
                    offset_date=0,
                    add_offset=0,
                    limit=batch_limit,
                    max_id=max_id,
                    min_id=min_id,
                    hash=0,
                ),
                timeout=timeout,
            )

            if not isinstance(res, (MessagesMessages, MessagesMessagesSlice, MessagesChannelMessages)):
                break

            # Ingest entities
            users = cast(list[Any], getattr(res, "users", []))
            chats = cast(list[Any], getattr(res, "chats", []))
            self.entities.ingest_users(list(users))
            self.entities.ingest_chats(list(chats))

            messages = cast(list[Any], getattr(res, "messages", []))

            if not messages:
                break

            for msg in messages:
                if limit is not None and total_yielded >= limit:
                    return
                yield msg
                total_yielded += 1

            # MessagesMessages (not slice) means we got all messages
            if isinstance(res, MessagesMessages):
                break

            # For slices, use the last message ID as offset for next batch
            last_msg_id = int(getattr(messages[-1], "id", 0) or 0)
            if last_msg_id == 0:
                break

            current_offset_id = last_msg_id

            # Safety: if we got fewer than requested, we're at the end
            if len(messages) < batch_limit:
                break

        # Persist entities after iteration
        self._persist_entities_cache(force=True)

    async def prime_entities(
        self,
        *,
        limit: int = 100,
        folder_id: int | None = None,
        timeout: float = 20.0,
    ) -> None:
        """
        Best-effort entity priming to populate access_hash cache.

        Why:
        - replies in private chats/channels require InputPeerUser/InputPeerChannel (access_hash)
        - short updates often contain only IDs without access_hash

        This method fetches a slice of dialogs, ingests users/chats into EntityCache.
        """
        from telecraft.tl.generated.functions import MessagesGetDialogs
        from telecraft.tl.generated.types import (
            InputPeerEmpty,
            MessagesDialogs,
            MessagesDialogsSlice,
        )

        res = await self.invoke_api(
            MessagesGetDialogs(
                flags=0,
                exclude_pinned=False,
                folder_id=int(folder_id) if folder_id is not None else None,
                offset_date=0,
                offset_id=0,
                offset_peer=InputPeerEmpty(),
                limit=int(limit),
                hash=0,
            ),
            timeout=timeout,
        )

        if isinstance(res, (MessagesDialogs, MessagesDialogsSlice)):
            users = cast(list[Any], getattr(res, "users", []))
            chats = cast(list[Any], getattr(res, "chats", []))
            self.entities.ingest_users(list(users))
            self.entities.ingest_chats(list(chats))
            self._persist_entities_cache(force=True)

    async def get_history(
        self,
        peer: PeerRef,
        *,
        limit: int = 50,
        timeout: float = 20.0,
    ) -> list[Any]:
        """
        Best-effort wrapper around messages.getHistory that also ingests users/chats into EntityCache.
        """
        from telecraft.tl.generated.types import MessagesMessages, MessagesMessagesSlice

        p = await self.resolve_peer(peer, timeout=timeout)
        try:
            input_peer = self.entities.input_peer(p)
        except EntityCacheError:
            await self._prime_entities_for_reply(want=p, timeout=timeout)
            input_peer = self.entities.input_peer(p)

        res = await self.invoke_api(
            MessagesGetHistory(
                peer=input_peer,
                offset_id=0,
                offset_date=0,
                add_offset=0,
                limit=int(limit),
                max_id=0,
                min_id=0,
                hash=0,
            ),
            timeout=timeout,
        )
        # messages.Messages also carries users/chats.
        self._ingest_from_updates_result(res)
        if isinstance(res, (MessagesMessages, MessagesMessagesSlice)):
            msgs = getattr(res, "messages", None)
            return list(msgs) if isinstance(msgs, list) else []
        return []

    async def send_code(self, phone_number: str, *, timeout: float = 20.0) -> AuthSentCode:
        """
        Start user login: request an SMS/Telegram login code.
        """
        if self._init is None or self._init.api_hash is None:
            raise MtprotoClientError(
                "ClientInit(api_id=..., api_hash=...) is required for send_code"
            )

        settings = CodeSettings(
            flags=0,
            allow_flashcall=False,
            current_number=True,
            allow_app_hash=True,
            allow_missed_call=False,
            allow_firebase=False,
            unknown_number=False,
            logout_tokens=None,
            token=None,
            app_sandbox=None,
        )

        res = await self.invoke_api(
            AuthSendCode(
                phone_number=phone_number,
                api_id=self._init.api_id,
                api_hash=self._init.api_hash,
                settings=settings,
            ),
            timeout=timeout,
        )

        if isinstance(res, AuthSentCode):
            return res
        if isinstance(res, AuthSentCodeSuccess):
            raise MtprotoClientError("send_code returned auth.sentCodeSuccess (already authorized)")
        if isinstance(res, AuthSentCodePaymentRequired):
            raise MtprotoClientError("send_code requires payment (auth.sentCodePaymentRequired)")
        raise MtprotoClientError(f"Unexpected auth.sendCode result: {type(res).__name__}")

    async def sign_in(
        self,
        *,
        phone_number: str,
        phone_code_hash: str | bytes,
        phone_code: str,
        timeout: float = 20.0,
    ) -> AuthAuthorization | AuthAuthorizationSignUpRequired:
        """
        Complete login with the code.
        """
        res = await self.invoke_api(
            AuthSignIn(
                flags=0,
                phone_number=phone_number,
                phone_code_hash=phone_code_hash,
                phone_code=phone_code,
                email_verification=None,
            ),
            timeout=timeout,
        )
        if isinstance(res, (AuthAuthorization, AuthAuthorizationSignUpRequired)):
            return res
        raise MtprotoClientError(f"Unexpected auth.signIn result: {type(res).__name__}")

    async def sign_up(
        self,
        *,
        phone_number: str,
        phone_code_hash: str | bytes,
        first_name: str,
        last_name: str = "",
        timeout: float = 20.0,
    ) -> AuthAuthorization:
        res = await self.invoke_api(
            AuthSignUp(
                flags=0,
                no_joined_notifications=False,
                phone_number=phone_number,
                phone_code_hash=phone_code_hash,
                first_name=first_name,
                last_name=last_name,
            ),
            timeout=timeout,
        )
        if isinstance(res, AuthAuthorization):
            return res
        raise MtprotoClientError(f"Unexpected auth.signUp result: {type(res).__name__}")

    async def check_password(self, password: str, *, timeout: float = 20.0) -> AuthAuthorization:
        """
        Complete login for accounts with 2FA enabled (SESSION_PASSWORD_NEEDED).
        """
        pw_state = await self.invoke_api(AccountGetPassword(), timeout=timeout)
        # account.getPassword returns account.Password, but generated type name is AccountPassword.
        from telecraft.tl.generated.types import AccountPassword

        if not isinstance(pw_state, AccountPassword):
            raise MtprotoClientError(
                f"Unexpected account.getPassword result: {type(pw_state).__name__}"
            )

        try:
            check = make_input_check_password_srp(password=password, password_state=pw_state)
        except SrpError as e:
            raise MtprotoClientError(f"Failed to compute SRP params: {e}") from e

        res = await self.invoke_api(AuthCheckPassword(password=check), timeout=timeout)
        if isinstance(res, AuthAuthorization):
            return res
        raise MtprotoClientError(f"Unexpected auth.checkPassword result: {type(res).__name__}")

    async def _persist_session(self) -> None:
        if self._session_path is None:
            return
        if self._state is None:
            return

        host, port = self._endpoint()
        sess = MtprotoSession(
            dc_id=self._dc_id,
            host=host,
            port=port,
            framing=self._framing_name,
            auth_key=self._state.auth_key,
            server_salt=self._state.server_salt,
            session_id=None,
        )
        save_session_file(self._session_path, sess)

