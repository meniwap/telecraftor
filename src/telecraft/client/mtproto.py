from __future__ import annotations

import asyncio
import time
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from telecraft.client.entities import EntityCache, load_entity_cache_file, save_entity_cache_file
from telecraft.mtproto.auth.handshake import exchange_auth_key
from telecraft.mtproto.auth.server_keys import DEFAULT_SERVER_KEYRING
from telecraft.mtproto.auth.srp import SrpError, make_input_check_password_srp
from telecraft.mtproto.core.msg_id import MsgIdGenerator
from telecraft.mtproto.core.state import MtprotoState
from telecraft.mtproto.rpc.sender import MtprotoEncryptedSender, ReceivedMessage
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
    AuthSendCode,
    AuthSignIn,
    AuthSignUp,
    HelpGetConfig,
    InitConnection,
    InvokeWithLayer,
    MessagesSendMessage,
    Ping,
    UsersGetUsers,
)
from telecraft.tl.generated.types import (
    AuthAuthorization,
    AuthAuthorizationSignUpRequired,
    AuthSentCode,
    AuthSentCodePaymentRequired,
    AuthSentCodeSuccess,
    CodeSettings,
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

        self.config: Any | None = None
        self.entities = EntityCache()

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
            invoke_api=lambda req: self.invoke_api(req, timeout=timeout)
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
        """
        res = await self.invoke_api(UsersGetUsers(id=[InputUserSelf()]), timeout=timeout)
        users = res if isinstance(res, list) else []
        self.entities.ingest_users(users)
        self._persist_entities_cache()
        return users[0] if users else None

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
        peer = self.entities.input_peer_user(int(user_id))
        return await self.send_message_peer(peer, text, timeout=timeout)

    async def send_message_channel(
        self, channel_id: int, text: str, *, timeout: float = 20.0
    ) -> Any:
        """
        Send a message to a channel/supergroup (requires access_hash in the entity cache).
        """
        peer = self.entities.input_peer_channel(int(channel_id))
        return await self.send_message_peer(peer, text, timeout=timeout)

    async def send_message_peer(self, peer: Any, text: str, *, timeout: float = 20.0) -> Any:
        """
        Low-level sendMessage wrapper for supported InputPeer* types.
        """
        from secrets import randbits

        return await self.invoke_api(
            MessagesSendMessage(
                flags=0,
                no_webpage=False,
                silent=False,
                background=False,
                clear_draft=False,
                noforwards=False,
                update_stickersets_order=False,
                invert_media=False,
                allow_paid_floodskip=False,
                peer=peer,
                reply_to=None,
                message=text,
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

    async def prime_entities(self, *, limit: int = 100, timeout: float = 20.0) -> None:
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
                folder_id=None,
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

