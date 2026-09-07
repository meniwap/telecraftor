from __future__ import annotations

import asyncio
import ipaddress
import logging
import math
import time
import types
from collections.abc import AsyncIterator, Awaitable, Callable, Coroutine
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
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
    is_self_peer_ref,
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
from telecraft.mtproto.rpc.sender import (
    DcMigrateError,
    FloodWaitConfig,
    MtprotoEncryptedSender,
    ReceivedMessage,
    ReceiverTerminated,
    RpcDecodeError,
    RpcErrorException,
    RpcSenderError,
    UpdatesRecoveryRequired,
)
from telecraft.mtproto.session import (
    MtprotoSession,
    SessionFileLock,
    SessionInUseError,
    acquire_session_file_lock,
    load_session_file,
    save_session_file,
)
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
    AuthLogOut,
    AuthSendCode,
    AuthSignIn,
    AuthSignUp,
    ChannelsCreateChannel,
    ChannelsDeleteMessages,
    ChannelsEditAdmin,
    ChannelsEditBanned,
    ChannelsGetFullChannel,
    ChannelsGetParticipant,
    ChannelsGetParticipants,
    ChannelsInviteToChannel,
    ChannelsJoinChannel,
    ChannelsLeaveChannel,
    ChannelsReadHistory,
    ContactsBlock,
    ContactsGetBlocked,
    ContactsGetContacts,
    ContactsResolvePhone,
    ContactsResolveUsername,
    ContactsUnblock,
    HelpGetConfig,
    InitConnection,
    InvokeWithLayer,
    MessagesAddChatUser,
    MessagesCreateChat,
    MessagesDeleteExportedChatInvite,
    MessagesDeleteHistory,
    MessagesDeleteMessages,
    MessagesDeleteScheduledMessages,
    MessagesEditChatTitle,
    MessagesEditExportedChatInvite,
    MessagesEditMessage,
    MessagesExportChatInvite,
    MessagesForwardMessages,
    MessagesGetCommonChats,
    MessagesGetExportedChatInvites,
    MessagesGetFullChat,
    MessagesGetHistory,
    MessagesGetPollResults,
    MessagesGetScheduledHistory,
    MessagesReadHistory,
    MessagesSearch,
    MessagesSendMedia,
    MessagesSendMessage,
    MessagesSendReaction,
    MessagesSendScheduledMessages,
    MessagesSendVote,
    MessagesSetTyping,
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
    ChatAdminRights,
    ChatBannedRights,
    CodeSettings,
    ContactsResolvedPeer,
    InputUser,
    InputUserSelf,
    UpdateConfig,
)
from telecraft.version import __version__

logger = logging.getLogger(__name__)


class MtprotoClientError(Exception):
    pass


class UpdatesRecoveryExhaustedError(MtprotoClientError):
    """A poisoned update stream repeated after bounded fresh-connection recovery."""

    retryable = False

    def __init__(
        self,
        *,
        constructor_id: int | None,
        expected_type: str | None,
        path: str | None,
        position: int | None,
        attempts: int,
        repeat_count: int,
        consecutive_failure_count: int,
        last_error: BaseException | None = None,
    ) -> None:
        self.constructor_id = constructor_id
        self.expected_type = expected_type
        self.path = path
        self.position = position
        self.attempts = int(attempts)
        self.repeat_count = int(repeat_count)
        self.consecutive_failure_count = int(consecutive_failure_count)
        self.last_error = last_error
        constructor = (
            f"0x{constructor_id & 0xFFFFFFFF:08x}" if constructor_id is not None else "unknown"
        )
        location = path or "<unknown TL path>"
        super().__init__(
            "Telegram repeatedly returned an undecodable constructor after "
            f"{attempts} fresh TCP/session/layer recovery attempts "
            f"(constructor={constructor}, path={location}, repeats={repeat_count}, "
            f"consecutive_unknown_failures={consecutive_failure_count}). "
            "The updates checkpoint was preserved; update the Telecraft schema/decoder "
            "before restarting this stream."
        )
        if last_error is not None:
            self.__cause__ = last_error


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

_UPDATES_IDLE_RECOVERY_SECONDS = 15 * 60
_UNKNOWN_CONSTRUCTOR_RECOVERY_MAX_ATTEMPTS = 3
_UNKNOWN_CONSTRUCTOR_RECOVERY_INITIAL_BACKOFF_SECONDS = 0.25
_UNKNOWN_CONSTRUCTOR_RECOVERY_MAX_BACKOFF_SECONDS = 2.0
_UNKNOWN_CONSTRUCTOR_ACTIVE_DRAIN_GRACE_SECONDS = 0.1


@dataclass(slots=True)
class ClientInit:
    api_id: int = field(repr=False)
    api_hash: str | None = field(default=None, repr=False)
    device_model: str = "telecraft"
    system_version: str = "telecraft"
    app_version: str = __version__
    system_lang_code: str = "en"
    lang_pack: str = ""
    lang_code: str = "en"


@dataclass(frozen=True, slots=True)
class _UnknownConstructorReconnectSnapshot:
    sender: MtprotoEncryptedSender
    transport: TcpTransport
    auth_key: bytes
    server_salt: bytes
    msg_id_gen: MsgIdGenerator
    host: str
    port: int
    framing: Framing


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
        trust_legacy_updates_state: bool = False,
        strict_update_persistence: bool = True,
        flood_wait_config: FloodWaitConfig | None = None,
        lock_session: bool = True,
    ) -> None:
        if network not in {"test", "prod"}:
            raise MtprotoClientError("network must be 'test' or 'prod'")
        self._network = network
        self._dc_id = dc_id
        self._host = host
        self._host_is_explicit = host is not None
        self._port = port
        self._framing_name = framing
        self._session_path = Path(session_path) if session_path is not None else None
        self._init = init
        self._trust_legacy_updates_state = bool(trust_legacy_updates_state)
        self._strict_update_persistence = bool(strict_update_persistence)
        self._flood_wait_config = flood_wait_config or FloodWaitConfig()
        self._lock_session = bool(lock_session)
        self._session_file_lock: SessionFileLock | None = None
        self._updates_state_auth_key_id_alias: str | None = None
        self._dc_endpoints: dict[int, tuple[str, int]] = {}
        if host is not None:
            self._dc_endpoints[int(dc_id)] = (str(host), int(port))

        self._transport: TcpTransport | None = None
        self._sender: MtprotoEncryptedSender | None = None
        self._state: MtprotoState | None = None
        self._msg_id_gen: MsgIdGenerator | None = None
        self._did_init_connection: bool = False
        self._incoming: (
            asyncio.Queue[ReceivedMessage | ReceiverTerminated | UpdatesRecoveryRequired] | None
        ) = None
        self._updates_engine: UpdatesEngine | None = None
        self._updates_task: asyncio.Task[None] | None = None
        self._updates_out: asyncio.Queue[Any] | None = None
        self._updates_terminal: asyncio.Future[BaseException] | None = None
        self._updates_state_last_save: float = 0.0
        self._entities_last_save: float = 0.0
        self.last_persistence_error: BaseException | None = None
        # Best-effort "me" identity (used by higher-level layers
        # to classify self-authored messages).
        self.self_user_id: int | None = None

        self.config: Any | None = None
        self.entities = EntityCache()
        # Cross-DC helpers for media downloads (lazy).
        self._media_clients: dict[int, MtprotoClient] = {}
        # Entity priming guardrails (avoid spamming dialogs on repeated short updates).
        self._prime_lock = asyncio.Lock()
        self._prime_last_attempt: float = 0.0
        self._lifecycle_lock = asyncio.Lock()
        self._lifecycle_owner: asyncio.Task[Any] | None = None
        self._lifecycle_depth = 0
        self._updates_lock = asyncio.Lock()
        self._migration_lock = asyncio.Lock()
        self._invoke_condition = asyncio.Condition()
        self._active_invocations = 0
        self._migration_in_progress = False
        self._unknown_constructor_fingerprint: tuple[int, str] | None = None
        self._unknown_constructor_repeat_count = 0
        self._unknown_constructor_consecutive_failure_count = 0
        self._unknown_constructor_reconnect_attempt_count = 0
        self._deferred_cleanup_tasks: set[asyncio.Task[Any]] = set()
        self._deferred_cleanup_resources: list[Any] = []
        self._deferred_cleanup_task_resources: dict[asyncio.Task[Any], Any] = {}

    @property
    def is_connected(self) -> bool:
        sender = self._sender
        if self._transport is None or sender is None or self._state is None:
            return False
        return bool(getattr(sender, "is_healthy", True))

    @asynccontextmanager
    async def _lifecycle_serialized(
        self,
        *,
        timeout: float | None = None,
    ) -> AsyncIterator[None]:
        """Serialize lifecycle mutation while allowing same-task migration.

        ``asyncio.Lock`` is not re-entrant.  Lifecycle operations such as
        ``start_updates`` and ``log_out`` may legitimately receive a DC migrate
        response and continue into ``_perform_primary_dc_migration`` in the same
        task.  Tracking the owner makes that nested mutation safe without
        releasing lifecycle exclusivity to competing connect/close operations.
        """

        task = asyncio.current_task()
        if task is None:
            raise RuntimeError("Lifecycle serialization requires an asyncio task")
        if self._lifecycle_owner is task:
            self._lifecycle_depth += 1
            try:
                yield
            finally:
                self._lifecycle_depth -= 1
            return

        if timeout is None:
            await self._lifecycle_lock.acquire()
        else:
            if not math.isfinite(timeout) or timeout <= 0:
                raise asyncio.TimeoutError
            await asyncio.wait_for(self._lifecycle_lock.acquire(), timeout=timeout)
        self._lifecycle_owner = task
        self._lifecycle_depth = 1
        try:
            yield
        finally:
            if self._lifecycle_owner is not task or self._lifecycle_depth != 1:
                raise RuntimeError("Lifecycle serialization ownership was corrupted")
            self._lifecycle_depth = 0
            self._lifecycle_owner = None
            self._lifecycle_lock.release()

    def _retain_deferred_cleanup_resource(self, resource: Any) -> None:
        if all(existing is not resource for existing in self._deferred_cleanup_resources):
            self._deferred_cleanup_resources.append(resource)

    def _release_deferred_cleanup_resource(self, resource: Any) -> None:
        self._deferred_cleanup_resources = [
            existing for existing in self._deferred_cleanup_resources if existing is not resource
        ]

    def _track_background_task(
        self,
        coroutine: Coroutine[Any, Any, Any],
        *,
        label: str,
    ) -> asyncio.Task[Any]:
        """Own a task until completion and always consume its terminal exception."""

        task = asyncio.create_task(coroutine, name=f"telecraft:{label}")
        self._deferred_cleanup_tasks.add(task)

        def completed(done: asyncio.Task[Any]) -> None:
            self._deferred_cleanup_tasks.discard(done)
            self._deferred_cleanup_task_resources.pop(done, None)
            if done.cancelled():
                return
            # Retrieve the exception even when the deadline-owning caller has
            # already returned, avoiding "Task exception was never retrieved".
            _ = done.exception()

        task.add_done_callback(completed)
        return task

    async def _await_task_hard_bounded(
        self,
        task: asyncio.Task[Any],
        *,
        timeout: float,
    ) -> Any:
        """Wait at most ``timeout`` without waiting for cancellation acknowledgement."""

        if not math.isfinite(timeout) or timeout <= 0:
            raise asyncio.TimeoutError
        done, _pending = await asyncio.wait({task}, timeout=timeout)
        if task not in done:
            # Do not cancel here. A coroutine may suppress cancellation, and
            # wait_for would then violate the caller's hard deadline. The task
            # remains explicitly owned by _deferred_cleanup_tasks.
            raise asyncio.TimeoutError
        return task.result()

    def _spawn_resource_cleanup(self, resource: Any, *, label: str) -> asyncio.Task[Any]:
        # Retain the resource before publishing the task.  This keeps ownership
        # explicit even if task creation itself raises, and allows a failed close
        # to be retried by a later teardown/diagnostic path.
        self._retain_deferred_cleanup_resource(resource)

        async def close_owned_resource() -> None:
            try:
                await resource.close()
            except BaseException:
                self._retain_deferred_cleanup_resource(resource)
                raise
            else:
                self._release_deferred_cleanup_resource(resource)

        task = self._track_background_task(
            close_owned_resource(),
            label=label,
        )
        self._deferred_cleanup_task_resources[task] = resource
        return task

    def _track_resource_cleanup_after_tasks(
        self,
        resource: Any,
        *,
        tasks: tuple[asyncio.Task[Any], ...],
        label: str,
    ) -> asyncio.Task[Any]:
        """Close ``resource`` again after late candidate operations have settled.

        Recovery candidates are deliberately abandoned at a hard deadline even
        when a buggy transport coroutine suppresses cancellation.  The immediate
        close issued by the caller unblocks ordinary I/O, but a late ``connect``
        may publish a writer *after* that close.  Retaining a second cleanup owner
        closes anything installed by such a late completion without extending the
        recovery caller's wall-clock deadline.
        """

        self._retain_deferred_cleanup_resource(resource)

        async def close_after_tasks() -> None:
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            try:
                await resource.close()
            except BaseException:
                self._retain_deferred_cleanup_resource(resource)
                raise
            else:
                self._release_deferred_cleanup_resource(resource)

        task = self._track_background_task(close_after_tasks(), label=label)
        self._deferred_cleanup_task_resources[task] = resource
        return task

    async def _retry_deferred_cleanup_resources(
        self,
        *,
        errors: list[BaseException],
    ) -> None:
        """Retry failed cleanup without racing a still-active cleanup owner."""

        for task in list(self._deferred_cleanup_task_resources):
            if task.done():
                self._deferred_cleanup_task_resources.pop(task, None)
        for resource in list(self._deferred_cleanup_resources):
            if any(
                not task.done() and active is resource
                for task, active in self._deferred_cleanup_task_resources.items()
            ):
                continue
            try:
                await resource.close()
            except BaseException as exc:
                errors.append(exc)
            else:
                self._release_deferred_cleanup_resource(resource)

    def _endpoint(self) -> tuple[str, int]:
        return self._endpoint_for_dc(self._dc_id)

    def _endpoint_for_dc(self, dc_id: int) -> tuple[str, int]:
        dc_id = int(dc_id)
        if dc_id == int(self._dc_id) and self._host is not None:
            return self._host, self._port
        cached = self._dc_endpoints.get(dc_id)
        if cached is not None:
            return cached
        mapping = TEST_DCS if self._network == "test" else PROD_DCS
        host, port = mapping.get(dc_id, ("", 0))
        if not host:
            raise MtprotoClientError(f"Unknown DC: {dc_id} (network={self._network})")
        return host, port

    def _ingest_dc_config(self, config: Any) -> None:
        """Cache ordinary IPv4 TCP endpoints advertised by ``help.getConfig``."""

        options = getattr(config, "dc_options", None)
        if not isinstance(options, list):
            return
        discovered: dict[int, tuple[str, int]] = {}
        for option in options:
            # This transport does not implement IPv6, CDN authorization, or
            # MTProxy/obfuscated secrets.  Never select such an endpoint merely
            # because it appeared first in the server response.
            if any(
                bool(getattr(option, field, False))
                for field in ("ipv6", "media_only", "cdn", "tcpo_only")
            ):
                continue
            secret = getattr(option, "secret", None)
            if isinstance(secret, (bytes, bytearray)) and secret:
                continue
            try:
                option_dc = int(getattr(option, "id"))
                option_host_obj = getattr(option, "ip_address")
                if isinstance(option_host_obj, str):
                    option_host = option_host_obj
                elif isinstance(option_host_obj, (bytes, bytearray)):
                    option_host = bytes(option_host_obj).decode("ascii")
                else:
                    continue
                option_host = str(ipaddress.IPv4Address(option_host))
                option_port = int(getattr(option, "port"))
            except (AttributeError, TypeError, UnicodeDecodeError, ValueError):
                continue
            if option_dc <= 0 or not option_host or not (0 < option_port < 65536):
                continue
            discovered.setdefault(option_dc, (option_host, option_port))

        if not discovered:
            return
        self._dc_endpoints.update(discovered)
        if not self._host_is_explicit and int(self._dc_id) in discovered:
            self._host, self._port = discovered[int(self._dc_id)]

    @staticmethod
    def _recovery_signal_from_decode_error(error: RpcDecodeError) -> UpdatesRecoveryRequired:
        return UpdatesRecoveryRequired.from_decode_error(error)

    def _record_unknown_constructor_failure(
        self,
        signal: UpdatesRecoveryRequired,
    ) -> int:
        fingerprint = signal.fingerprint
        if fingerprint is None:
            # ``requires_reconnect`` is reserved for structured unknown-constructor
            # failures.  Keep a stable fallback so a malformed internal signal still
            # cannot defeat the process-wide circuit breaker.
            fingerprint = (-1, signal.path or "<unknown TL path>")
        self._unknown_constructor_consecutive_failure_count += 1
        if fingerprint == self._unknown_constructor_fingerprint:
            self._unknown_constructor_repeat_count += 1
        else:
            self._unknown_constructor_fingerprint = fingerprint
            self._unknown_constructor_repeat_count = 1
        return self._unknown_constructor_repeat_count

    def _clear_unknown_constructor_failures(self) -> None:
        self._unknown_constructor_fingerprint = None
        self._unknown_constructor_repeat_count = 0
        self._unknown_constructor_consecutive_failure_count = 0
        self._unknown_constructor_reconnect_attempt_count = 0

    def _recovery_exhausted(
        self,
        signal: UpdatesRecoveryRequired,
        *,
        attempts: int,
        last_error: BaseException | None,
    ) -> UpdatesRecoveryExhaustedError:
        return UpdatesRecoveryExhaustedError(
            constructor_id=signal.constructor_id,
            expected_type=signal.expected_type,
            path=signal.path,
            position=signal.position,
            attempts=attempts,
            repeat_count=self._unknown_constructor_repeat_count,
            consecutive_failure_count=self._unknown_constructor_consecutive_failure_count,
            last_error=last_error,
        )

    def _unknown_constructor_reconnect_snapshot(
        self,
    ) -> _UnknownConstructorReconnectSnapshot:
        state = self._state
        sender = self._sender
        transport = self._transport
        if state is None or sender is None or transport is None:
            raise MtprotoClientError("Cannot recover unknown constructor while disconnected")
        msg_id_gen = self._msg_id_gen or state.msg_id_gen
        host, port = self._endpoint()
        return _UnknownConstructorReconnectSnapshot(
            sender=sender,
            transport=transport,
            auth_key=bytes(state.auth_key),
            server_salt=bytes(state.server_salt),
            msg_id_gen=msg_id_gen,
            host=host,
            port=port,
            framing=_make_framing(self._framing_name),
        )

    def _begin_unknown_constructor_disconnect(
        self,
        snapshot: _UnknownConstructorReconnectSnapshot,
    ) -> None:
        """Poison synchronously and start both closes without waiting for them."""

        snapshot.sender.invalidate(
            RpcSenderError("MTProto connection invalidated after unknown constructor")
        )
        self._spawn_resource_cleanup(
            snapshot.sender,
            label="unknown-constructor-old-sender",
        )
        self._spawn_resource_cleanup(
            snapshot.transport,
            label="unknown-constructor-old-transport",
        )

    async def _perform_unknown_constructor_reconnect(
        self,
        *,
        snapshot: _UnknownConstructorReconnectSnapshot,
        timeout: float,
    ) -> None:
        """Connect and layer-initialize a private candidate before atomic adoption."""

        if self._init is None:
            raise MtprotoClientError(
                "ClientInit(api_id=...) is required for unknown-constructor recovery"
            )
        if not math.isfinite(timeout) or timeout <= 0:
            raise asyncio.TimeoutError

        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout

        def remaining() -> float:
            value = deadline - loop.time()
            if value <= 0:
                raise asyncio.TimeoutError
            return value

        candidate_transport: TcpTransport | None = None
        candidate_sender: MtprotoEncryptedSender | None = None
        candidate_operation_tasks: list[asyncio.Task[Any]] = []
        adopted = False
        try:
            candidate_transport = TcpTransport(
                endpoint=Endpoint(host=snapshot.host, port=snapshot.port),
                framing=snapshot.framing,
            )
            connect_task = self._track_background_task(
                candidate_transport.connect(),
                label="unknown-constructor-candidate-connect",
            )
            candidate_operation_tasks.append(connect_task)
            await self._await_task_hard_bounded(connect_task, timeout=remaining())

            candidate_state = MtprotoState(
                auth_key=snapshot.auth_key,
                server_salt=snapshot.server_salt,
                msg_id_gen=snapshot.msg_id_gen,
                # A new session id is mandatory: the previous session consumed an
                # undecodable envelope and must never be resumed.
                session_id=b"",
            )
            candidate_incoming: asyncio.Queue[
                ReceivedMessage | ReceiverTerminated | UpdatesRecoveryRequired
            ] = asyncio.Queue(maxsize=2048)
            candidate_sender = MtprotoEncryptedSender(
                candidate_transport,
                state=candidate_state,
                msg_id_gen=snapshot.msg_id_gen,
                incoming_queue=candidate_incoming,
                flood_wait_config=self._flood_wait_config,
            )

            # Invoke directly on the private candidate. Calling self.invoke() while
            # migration is announced would deadlock on _invoke_condition. A stubborn
            # transport cannot extend this hard wall-clock deadline.
            bootstrap_task = self._track_background_task(
                candidate_sender.invoke_tl(
                    wrap_with_layer_init(query=HelpGetConfig(), init=self._init),
                    timeout=remaining(),
                    flood_wait_config=self._flood_wait_config,
                ),
                label="unknown-constructor-candidate-layer-init",
            )
            candidate_operation_tasks.append(bootstrap_task)
            candidate_config = await self._await_task_hard_bounded(
                bootstrap_task,
                timeout=remaining(),
            )

            # Transactional adoption: no await occurs while connection ownership is
            # transferred, so cancellation cannot expose a half-published sender.
            self._transport = candidate_transport
            self._sender = candidate_sender
            self._state = candidate_state
            self._msg_id_gen = snapshot.msg_id_gen
            self._incoming = candidate_incoming
            self.config = candidate_config
            self._did_init_connection = True
            adopted = True
            self._ingest_dc_config(candidate_config)

            # The auth key is unchanged; persisting a newly learned salt/endpoint is
            # useful but not required for protocol correctness.
            try:
                await self._persist_session()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning(
                    "Failed to persist the replacement MTProto connection metadata",
                    exc_info=True,
                )
        finally:
            if not adopted:
                # Request cancellation, but never await acknowledgement on the
                # recovery path: a coroutine may suppress it.  Both tasks remain
                # owned until their done callbacks consume the outcome.
                for operation_task in candidate_operation_tasks:
                    if not operation_task.done():
                        operation_task.cancel()
                if candidate_sender is not None:
                    candidate_sender.invalidate(
                        RpcSenderError("Unsuccessful MTProto recovery candidate")
                    )
                    self._spawn_resource_cleanup(
                        candidate_sender,
                        label="unknown-constructor-candidate-sender-cleanup",
                    )
                    self._track_resource_cleanup_after_tasks(
                        candidate_sender,
                        tasks=tuple(candidate_operation_tasks),
                        label="unknown-constructor-candidate-sender-final-cleanup",
                    )
                if candidate_transport is not None:
                    # Close transport immediately. A connect/bootstrap coroutine
                    # that suppresses cancellation may be blocked on this exact I/O;
                    # waiting for it first creates a cleanup deadlock.
                    self._spawn_resource_cleanup(
                        candidate_transport,
                        label="unknown-constructor-candidate-transport-cleanup",
                    )
                    self._track_resource_cleanup_after_tasks(
                        candidate_transport,
                        tasks=tuple(candidate_operation_tasks),
                        label="unknown-constructor-candidate-transport-final-cleanup",
                    )

    async def _reconnect_for_unknown_constructor(
        self,
        *,
        timeout: float,
        poisoned_sender: MtprotoEncryptedSender | None = None,
    ) -> None:
        """Serialize same-DC socket replacement without deadlocking old RPCs."""

        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout

        def remaining() -> float:
            value = deadline - loop.time()
            if value <= 0:
                raise asyncio.TimeoutError
            return value

        async with self._lifecycle_serialized(timeout=remaining()):
            await asyncio.wait_for(self._migration_lock.acquire(), timeout=remaining())
            migration_announced = False
            try:
                # Another concurrent next-call recovery may already have replaced
                # exactly the sender observed by this caller.
                if poisoned_sender is not None and self._sender is not poisoned_sender:
                    return
                snapshot = self._unknown_constructor_reconnect_snapshot()
                async with self._invoke_condition:
                    self._migration_in_progress = True
                    migration_announced = True

                # Poison and initiate TCP close before waiting on invocations. This
                # wakes FloodWait retries synchronously and releases blocked sends as
                # soon as transport.close starts.
                self._begin_unknown_constructor_disconnect(snapshot)
                await asyncio.sleep(0)

                drain_deadline = min(
                    deadline,
                    loop.time() + _UNKNOWN_CONSTRUCTOR_ACTIVE_DRAIN_GRACE_SECONDS,
                )
                async with self._invoke_condition:
                    while self._active_invocations:
                        drain_remaining = drain_deadline - loop.time()
                        if drain_remaining <= 0:
                            logger.warning(
                                "Proceeding with fresh MTProto connection while %d poisoned "
                                "invocation(s) finish on the isolated old sender",
                                self._active_invocations,
                            )
                            break
                        try:
                            await asyncio.wait_for(
                                self._invoke_condition.wait(),
                                timeout=drain_remaining,
                            )
                        except asyncio.TimeoutError:
                            logger.warning(
                                "Proceeding with fresh MTProto connection while %d poisoned "
                                "invocation(s) finish on the isolated old sender",
                                self._active_invocations,
                            )
                            break

                await self._perform_unknown_constructor_reconnect(
                    snapshot=snapshot,
                    timeout=remaining(),
                )
            finally:
                if migration_announced:
                    async with self._invoke_condition:
                        self._migration_in_progress = False
                        self._invoke_condition.notify_all()
                self._migration_lock.release()

    async def _run_after_unknown_constructor(
        self,
        signal: UpdatesRecoveryRequired,
        *,
        operation: Callable[[], Awaitable[Any]],
        restore_checkpoint: Callable[[], None] | None,
        timeout: float,
    ) -> Any:
        """Run an update operation only after bounded fresh-connection recovery."""

        if not signal.requires_reconnect:
            return await operation()

        current_signal = signal
        repeat_count = self._record_unknown_constructor_failure(current_signal)
        # A prior exhausted run on this client is a global circuit breaker. This
        # matters for bot runners that reconnect the same client object forever.
        if (
            repeat_count > _UNKNOWN_CONSTRUCTOR_RECOVERY_MAX_ATTEMPTS
            or self._unknown_constructor_consecutive_failure_count
            > _UNKNOWN_CONSTRUCTOR_RECOVERY_MAX_ATTEMPTS
        ):
            if restore_checkpoint is not None:
                restore_checkpoint()
            raise self._recovery_exhausted(
                current_signal,
                attempts=self._unknown_constructor_reconnect_attempt_count,
                last_error=None,
            )

        last_error: BaseException | None = None
        while True:
            if restore_checkpoint is not None:
                restore_checkpoint()
            if (
                self._unknown_constructor_reconnect_attempt_count
                >= _UNKNOWN_CONSTRUCTOR_RECOVERY_MAX_ATTEMPTS
                or self._unknown_constructor_consecutive_failure_count
                > _UNKNOWN_CONSTRUCTOR_RECOVERY_MAX_ATTEMPTS
            ):
                raise self._recovery_exhausted(
                    current_signal,
                    attempts=self._unknown_constructor_reconnect_attempt_count,
                    last_error=last_error,
                )
            attempt = self._unknown_constructor_reconnect_attempt_count + 1
            attempt_poisoned_sender = self._sender
            delay = (
                0.0
                if attempt == 1
                else min(
                    _UNKNOWN_CONSTRUCTOR_RECOVERY_MAX_BACKOFF_SECONDS,
                    _UNKNOWN_CONSTRUCTOR_RECOVERY_INITIAL_BACKOFF_SECONDS * (2 ** (attempt - 2)),
                )
            )
            if delay > 0:
                await asyncio.sleep(delay)
            logger.warning(
                "Recovering poisoned MTProto update stream on a fresh connection "
                "(attempt=%d/%d, constructor=%s, path=%s)",
                attempt,
                _UNKNOWN_CONSTRUCTOR_RECOVERY_MAX_ATTEMPTS,
                (
                    f"0x{current_signal.constructor_id & 0xFFFFFFFF:08x}"
                    if current_signal.constructor_id is not None
                    else "unknown"
                ),
                current_signal.path,
            )
            self._unknown_constructor_reconnect_attempt_count = attempt

            try:
                await self._reconnect_for_unknown_constructor(
                    timeout=timeout,
                    poisoned_sender=attempt_poisoned_sender,
                )
            except asyncio.CancelledError:
                raise
            except RpcDecodeError as exc:
                if not exc.requires_reconnect:
                    raise
                last_error = exc
                current_signal = self._recovery_signal_from_decode_error(exc)
                self._record_unknown_constructor_failure(current_signal)
                continue
            except Exception as exc:  # connection/bootstrap failures are retryable here
                last_error = exc
                logger.warning(
                    "Fresh MTProto connection initialization failed during unknown-"
                    "constructor recovery",
                    exc_info=True,
                )
                continue

            try:
                result = await operation()
            except asyncio.CancelledError:
                raise
            except RpcDecodeError as exc:
                if not exc.requires_reconnect:
                    raise
                last_error = exc
                current_signal = self._recovery_signal_from_decode_error(exc)
                self._record_unknown_constructor_failure(current_signal)
                continue
            except RpcSenderError as exc:
                sender = self._sender
                if sender is not None and sender.is_healthy:
                    raise
                last_error = exc
                logger.warning(
                    "Replacement MTProto connection terminated during updates recovery",
                    exc_info=True,
                )
                continue
            else:
                return result

    async def connect(self, *, timeout: float = 30.0) -> None:
        async with self._lifecycle_serialized():
            if self.is_connected:
                return
            if any(
                value is not None
                for value in (
                    self._transport,
                    self._sender,
                    self._state,
                    self._updates_task,
                )
            ):
                await self._teardown_locked(persist=False, raise_errors=False)

            if (
                self._session_path is not None
                and self._lock_session
                and self._session_file_lock is None
            ):
                try:
                    self._session_file_lock = acquire_session_file_lock(self._session_path)
                except SessionInUseError as exc:
                    raise MtprotoClientError(str(exc)) from exc

            try:
                # If we have a session file, treat it as authoritative for endpoint/framing.
                # This avoids common "session mismatch" errors when a previous login migrated DCs.
                sess: MtprotoSession | None = None
                if self._session_path is not None and self._session_path.exists():
                    sess = load_session_file(self._session_path)
                    self._dc_id = int(sess.dc_id)
                    self._host = str(sess.host)
                    self._port = int(sess.port)
                    self._framing_name = str(sess.framing)
                    self._updates_state_auth_key_id_alias = sess.updates_state_auth_key_id_alias
                    self._dc_endpoints[self._dc_id] = (self._host, self._port)
                else:
                    self._updates_state_auth_key_id_alias = None

                host, port = self._endpoint()
                framing = _make_framing(self._framing_name)
            except BaseException:
                session_file_lock = self._session_file_lock
                self._session_file_lock = None
                if session_file_lock is not None:
                    session_file_lock.release()
                raise
            transport = TcpTransport(endpoint=Endpoint(host=host, port=port), framing=framing)
            # Publish the transport early so every failure path can use the same teardown.
            # is_connected remains false until sender and state are healthy as well.
            self._transport = transport
            try:
                await transport.connect()

                auth_key: bytes
                server_salt: bytes
                server_time: int | None = None
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
                    server_time = int(res.server_time)

                msg_id_gen = MsgIdGenerator(server_time=server_time)
                state = MtprotoState(
                    auth_key=auth_key,
                    server_salt=server_salt,
                    msg_id_gen=msg_id_gen,
                    # NOTE: we intentionally do not persist/reuse session_id across process
                    # restarts unless seqno is also persisted.
                    session_id=b"",
                )

                incoming: asyncio.Queue[
                    ReceivedMessage | ReceiverTerminated | UpdatesRecoveryRequired
                ] = asyncio.Queue(maxsize=2048)
                sender = MtprotoEncryptedSender(
                    transport,
                    state=state,
                    msg_id_gen=msg_id_gen,
                    incoming_queue=incoming,
                    flood_wait_config=self._flood_wait_config,
                )

                self._sender = sender
                self._state = state
                self._msg_id_gen = msg_id_gen
                self._incoming = incoming

                # Access hashes are scoped to the authorization that produced
                # them.  A fresh auth key must never load a same-named cache left
                # behind by an older login; doing so causes CHANNEL_INVALID and
                # PEER_ID_INVALID failures. Existing sessions may restore theirs.
                if sess is not None:
                    self._load_entities_cache()
                else:
                    # A new authorization at a reused path must not inherit any
                    # account-scoped sidecar left by the previous session.
                    self._clear_session_sidecars()
                    self.entities = EntityCache(auth_key_id=self._auth_key_id_hex())

                # Bootstrap as a "real" API client.
                if self._init is not None:
                    self.config = await self.invoke_with_layer(HelpGetConfig(), timeout=timeout)
                    self._ingest_dc_config(self.config)
                    self._did_init_connection = True

                await self._persist_session()
            except BaseException:
                await self._teardown_locked(persist=False, raise_errors=False)
                raise

    async def close(self) -> None:
        async with self._lifecycle_serialized():
            await self._teardown_locked(persist=True, raise_errors=True)

    async def _teardown_locked(self, *, persist: bool, raise_errors: bool) -> None:
        """Close every runtime resource; caller must hold lifecycle serialization."""

        errors: list[BaseException] = []
        if persist:
            try:
                await self._persist_session()
            except BaseException as exc:  # cleanup must continue even on cancellation
                errors.append(exc)
            try:
                self._persist_entities_cache(force=True)
            except BaseException as exc:
                errors.append(exc)

        update_task = self._updates_task
        try:
            await self.stop_updates()
        except BaseException as exc:
            errors.append(exc)
        if (
            update_task is not None
            and update_task is not asyncio.current_task()
            and not update_task.done()
        ):
            update_task.cancel()
            try:
                await update_task
            except asyncio.CancelledError:
                pass
            except BaseException as exc:
                errors.append(exc)

        media_clients = list(self._media_clients.values())
        self._media_clients.clear()
        for client in media_clients:
            try:
                await client.close()
            except BaseException as exc:
                errors.append(exc)
            else:
                self._release_deferred_cleanup_resource(client)

        sender = self._sender
        if sender is not None:
            try:
                await sender.close()
            except BaseException as exc:
                errors.append(exc)
            else:
                self._release_deferred_cleanup_resource(sender)

        transport = self._transport
        if transport is not None:
            try:
                await transport.close()
            except BaseException as exc:
                errors.append(exc)
            else:
                self._release_deferred_cleanup_resource(transport)

        # A timed-out migration may have left an old sender, transport, child,
        # or unsuccessful candidate in a tracked cleanup task.  Never double-
        # close an actively owned resource; retry those whose prior close task
        # has already failed and completed.
        await self._retry_deferred_cleanup_resources(errors=errors)

        self._sender = None
        self._transport = None
        self._state = None
        self._msg_id_gen = None
        self._incoming = None
        self._updates_engine = None
        self._updates_task = None
        self._updates_out = None
        self._updates_terminal = None
        self._did_init_connection = False
        self.config = None

        session_file_lock = self._session_file_lock
        self._session_file_lock = None
        if session_file_lock is not None:
            try:
                session_file_lock.release()
            except BaseException as exc:
                errors.append(exc)

        if errors and raise_errors:
            raise errors[0]

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

    async def invoke(
        self,
        req: Any,
        *,
        timeout: float = 20.0,
        flood_wait_config: FloodWaitConfig | None = None,
    ) -> Any:
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be a positive finite number")
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout

        def remaining() -> float:
            value = deadline - loop.time()
            if value <= 0:
                raise RpcSenderError(f"Timed out waiting for response (total deadline={timeout}s)")
            return value

        try:
            await asyncio.wait_for(
                self._invoke_condition.acquire(),
                timeout=remaining(),
            )
        except asyncio.TimeoutError as exc:
            raise RpcSenderError(
                f"Timed out waiting for response (total deadline={timeout}s)"
            ) from exc
        try:
            while self._migration_in_progress:
                try:
                    await asyncio.wait_for(
                        self._invoke_condition.wait(),
                        timeout=remaining(),
                    )
                except asyncio.TimeoutError as exc:
                    raise RpcSenderError(
                        f"Timed out waiting for response (total deadline={timeout}s)"
                    ) from exc
            sender = self._sender
            if sender is None:
                raise MtprotoClientError("Not connected")
            sender_timeout = remaining()
            self._active_invocations += 1
        finally:
            self._invoke_condition.release()

        async def invoke_owned() -> Any:
            try:
                return await sender.invoke_tl(
                    req,
                    timeout=sender_timeout,
                    flood_wait_config=flood_wait_config,
                )
            finally:
                async with self._invoke_condition:
                    self._active_invocations -= 1
                    self._invoke_condition.notify_all()

        invoke_task = self._track_background_task(
            invoke_owned(),
            label="invoke",
        )
        try:
            return await self._await_task_hard_bounded(
                invoke_task,
                timeout=remaining(),
            )
        except asyncio.TimeoutError as exc:
            raise RpcSenderError(
                f"Timed out waiting for response (total deadline={timeout}s)"
            ) from exc

    async def invoke_with_layer(self, req: Any, *, timeout: float = 20.0) -> Any:
        if self._init is None:
            raise MtprotoClientError("ClientInit(api_id=...) is required for invoke_with_layer")
        wrapped = wrap_with_layer_init(query=req, init=self._init)
        return await self.invoke(wrapped, timeout=timeout)

    async def invoke_api(self, req: Any, *, timeout: float = 20.0) -> Any:
        """
        Invoke a regular API method after we've performed initConnection/invokeWithLayer once.

        ``timeout`` is a total deadline, including one Telegram-requested DC
        migration and FloodWait sleeps.  Migration errors are rejection
        responses, so retrying the rejected RPC once on the instructed DC cannot
        duplicate a successfully executed non-idempotent request.
        """
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout

        def remaining() -> float:
            value = deadline - loop.time()
            if value <= 0:
                raise MtprotoClientError(
                    f"Timed out invoking API request (total deadline={timeout}s)"
                )
            return value

        for attempt in range(2):
            try:
                if self._init is not None and not self._did_init_connection:
                    # Perform one bootstrap call to "register" the client.
                    self.config = await self.invoke_with_layer(HelpGetConfig(), timeout=remaining())
                    self._ingest_dc_config(self.config)
                    self._did_init_connection = True
                result = await self.invoke(req, timeout=remaining())
                if isinstance(req, HelpGetConfig):
                    self.config = result
                    self._ingest_dc_config(result)
                return result
            except DcMigrateError as exc:
                if attempt > 0:
                    raise
                if exc.kind == "FILE":
                    route_timeout = remaining()
                    try:
                        target = await self._client_for_dc(
                            exc.dc_id,
                            timeout=route_timeout,
                        )
                    except asyncio.TimeoutError as timeout_exc:
                        raise MtprotoClientError(
                            f"Timed out routing FILE request to DC {exc.dc_id}"
                        ) from timeout_exc
                    return await target.invoke_api(req, timeout=remaining())
                migration_timeout = remaining()
                try:
                    await self._migrate_primary_dc(
                        exc.dc_id,
                        kind=exc.kind,
                        timeout=migration_timeout,
                    )
                except asyncio.TimeoutError as timeout_exc:
                    raise MtprotoClientError(
                        f"Timed out migrating {exc.kind} request to DC {exc.dc_id}"
                    ) from timeout_exc

        raise AssertionError("unreachable")

    async def ping(self, *, timeout: float = 20.0) -> Any:
        # ping doesn't need initConnection/invokeWithLayer.
        from secrets import randbits

        ping_id = randbits(63)
        return await self.invoke(Ping(ping_id=ping_id), timeout=timeout)

    async def log_out(self, *, timeout: float = 20.0) -> Any:
        """Log out remotely, disconnect, and remove the now-invalid local authorization."""

        async with self._lifecycle_serialized():
            result = await self.invoke_api(AuthLogOut(), timeout=timeout)
            await self._teardown_locked(persist=False, raise_errors=False)
            # Keep invalid-session deletion and identity reset in the same
            # critical section so a waiting connect cannot reload the logged-
            # out authorization and then lose files underneath itself.
            self._clear_local_session_files()
            self.entities = EntityCache()
            self.self_user_id = None
            return result

    async def start_updates(self, *, timeout: float = 20.0) -> None:
        """
        Start updates engine and background consumer.

        This must be called after login if you want to receive user updates reliably.
        """
        # Lock order is always lifecycle -> updates. This prevents two consumers
        # from being published concurrently and prevents close from tearing down
        # the sender while initialization is awaiting updates.getDifference.
        async with self._lifecycle_serialized():
            async with self._updates_lock:
                await self._start_updates_locked(timeout=timeout)

    async def _start_updates_locked(self, *, timeout: float) -> None:
        if self._updates_task is not None:
            if not self._updates_task.done():
                return
            await self._stop_updates_locked()
        if self._incoming is None:
            raise MtprotoClientError("Not connected")
        if self._init is None:
            raise MtprotoClientError("ClientInit(api_id=...) is required to start updates")

        updates_out: asyncio.Queue[Any] = asyncio.Queue(maxsize=4096)
        updates_terminal: asyncio.Future[BaseException] = asyncio.get_running_loop().create_future()
        updates_engine = UpdatesEngine(
            invoke_api=lambda req: self.invoke_api(req, timeout=timeout),
            resolve_input_channel=lambda channel_id: self.entities.input_channel_or_none(
                int(channel_id)
            ),
        )
        initial_state = self._load_updates_state()

        async def initialize() -> UpdatesState:
            return await updates_engine.initialize(initial_state=initial_state)

        try:
            await initialize()
        except RpcDecodeError as exc:
            if not exc.requires_reconnect:
                raise
            # Startup catch-up runs before the consumer is published. Recover it
            # synchronously so a poisoned sender is never returned by start_updates,
            # and retry from the exact durable checkpoint supplied above.
            await self._run_after_unknown_constructor(
                self._recovery_signal_from_decode_error(exc),
                operation=initialize,
                restore_checkpoint=(
                    (lambda: updates_engine.restore(initial_state))
                    if initial_state is not None
                    else None
                ),
                timeout=timeout,
            )
        initial_catch_up = updates_engine.take_initial_catch_up()
        self._updates_out = updates_out
        self._updates_terminal = updates_terminal
        self._updates_engine = updates_engine
        try:
            if initial_state is None:
                # A fresh getState baseline has no catch-up batch to drive the
                # normal dispatch checkpoint.  Persist it before returning from
                # start_updates so a crash during an otherwise idle session
                # cannot restart from a newer getState and skip that interval.
                self._persist_updates_state(force=True)
            self._updates_task = asyncio.create_task(
                self._updates_loop(
                    initial_catch_up=initial_catch_up,
                    config_refresh_timeout=timeout,
                )
            )
        except BaseException:
            self._updates_out = None
            self._updates_terminal = None
            self._updates_engine = None
            raise

    async def stop_updates(self) -> None:
        async with self._updates_lock:
            await self._stop_updates_locked()

    async def _stop_updates_locked(self) -> None:
        task = self._updates_task
        if task is not None:
            if task is not asyncio.current_task() and not task.done():
                task.cancel()
            if task is not asyncio.current_task():
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            self._updates_task = None
            # The loop rolls back an interrupted batch before cancellation escapes,
            # so this forced save can never acknowledge an update that was not queued.
            self._persist_updates_state(force=True)
        self._finish_updates(MtprotoClientError("Updates stopped"))

    async def recv_update(self) -> Any:
        """Return the next accepted update.

        Delivery is checkpoint-on-enqueue: the persisted pts/qts cursor advances
        only after the complete batch has entered the in-memory output queue.  A
        process crash after that checkpoint but before application processing can
        therefore lose an application-level delivery.  Consumers requiring a
        durable business acknowledgement must persist/idempotently deduplicate
        their own work; Telecraft guarantees protocol recovery, not exactly-once
        application processing.
        """

        updates_out = self._updates_out
        terminal = self._updates_terminal
        if updates_out is None or terminal is None:
            raise MtprotoClientError("Updates not started (call start_updates())")

        # Preserve already accepted updates if the receiver terminated immediately
        # afterwards; once the queue is drained, every waiter sees the terminal error.
        try:
            return updates_out.get_nowait()
        except asyncio.QueueEmpty:
            pass
        if terminal.done():
            raise terminal.result()

        get_task = asyncio.create_task(updates_out.get())
        try:
            done, _pending = await asyncio.wait(
                {get_task, terminal},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if get_task in done:
                return get_task.result()
            get_task.cancel()
            try:
                await get_task
            except asyncio.CancelledError:
                pass
            raise terminal.result()
        except asyncio.CancelledError:
            get_task.cancel()
            try:
                await get_task
            except asyncio.CancelledError:
                pass
            raise
        finally:
            if not get_task.done():
                get_task.cancel()

    def _finish_updates(self, error: BaseException) -> None:
        terminal = self._updates_terminal
        if terminal is not None and not terminal.done():
            terminal.set_result(error)

    async def _updates_loop(
        self,
        *,
        initial_catch_up: tuple[UpdatesState, AppliedUpdates] | None = None,
        config_refresh_timeout: float = 20.0,
    ) -> None:
        assert self._incoming is not None
        assert self._updates_out is not None
        assert self._updates_engine is not None
        updates_out = self._updates_out
        updates_engine = self._updates_engine

        async def dispatch(
            *,
            checkpoint: UpdatesState,
            applied: AppliedUpdates,
        ) -> None:
            try:
                if any(isinstance(update, UpdateConfig) for update in applied.updates):
                    try:
                        await self.invoke_api(
                            HelpGetConfig(),
                            timeout=config_refresh_timeout,
                        )
                        # Keep the refreshed primary endpoint durable for a
                        # restart even if the process exits before normal close.
                        await self._persist_session()
                    except asyncio.CancelledError:
                        raise
                    except RpcDecodeError as exc:
                        if exc.requires_reconnect:
                            raise
                        logger.warning(
                            "Failed to decode Telegram DC config after updateConfig",
                            exc_info=True,
                        )
                    except Exception:
                        # Endpoint refresh is operational metadata.  A transient
                        # failure must not discard or permanently stall the
                        # otherwise valid update stream; the next updateConfig or
                        # reconnect will retry it.
                        logger.warning(
                            "Failed to refresh Telegram DC config after updateConfig",
                            exc_info=True,
                        )

                self.entities.ingest_users(applied.users)
                self.entities.ingest_chats(applied.chats)
                self._persist_entities_cache()

                # Backpressure is deliberate: advancing persisted state while silently
                # dropping a full output queue makes that update unrecoverable forever.
                for updates in (applied.new_messages, applied.updates):
                    for update in updates:
                        await updates_out.put(update)
                self._persist_updates_state()
            except BaseException:
                updates_engine.restore(checkpoint)
                raise

        def cursor_progressed(before: UpdatesState, after: UpdatesState) -> bool:
            # ``date`` is merely the next difference query timestamp. Telegram can
            # advance it in an empty response while immediately repeating the same
            # poisoned live update, so date-only movement is not health evidence.
            return bool(
                before.pts != after.pts
                or before.qts != after.qts
                or before.seq != after.seq
                or before.channel_pts != after.channel_pts
            )

        def clear_circuit_after_success(
            *,
            checkpoint: UpdatesState,
            applied: AppliedUpdates,
            independently_healthy_live_input: bool,
        ) -> None:
            if (
                self._unknown_constructor_fingerprint is None
                or not independently_healthy_live_input
            ):
                return
            has_payload = bool(applied.new_messages or applied.updates)
            live_cursor_progress = cursor_progressed(
                checkpoint,
                updates_engine.checkpoint(),
            )
            # Difference output—even nonempty output—is part of recovery and can
            # be followed immediately by the same poisoned live envelope. Reset
            # only after an independently received live input was decoded, its
            # payload was delivered/persisted, and a durable non-date cursor moved.
            if has_payload and live_cursor_progress:
                self._clear_unknown_constructor_failures()

        async def recover_poisoned_connection(
            *,
            signal: UpdatesRecoveryRequired,
            checkpoint: UpdatesState,
        ) -> None:
            async def recover_and_dispatch() -> None:
                applied = await updates_engine.recover()
                await dispatch(checkpoint=checkpoint, applied=applied)

            await self._run_after_unknown_constructor(
                signal,
                operation=recover_and_dispatch,
                restore_checkpoint=lambda: updates_engine.restore(checkpoint),
                timeout=config_refresh_timeout,
            )

        async def apply_and_dispatch_with_poison_recovery(
            *,
            operation: Callable[[], Awaitable[AppliedUpdates]],
            checkpoint: UpdatesState,
            independently_healthy_live_input: bool = False,
        ) -> None:
            try:
                applied = await operation()
                await dispatch(checkpoint=checkpoint, applied=applied)
                clear_circuit_after_success(
                    checkpoint=checkpoint,
                    applied=applied,
                    independently_healthy_live_input=independently_healthy_live_input,
                )
            except RpcDecodeError as exc:
                updates_engine.restore(checkpoint)
                if not exc.requires_reconnect:
                    raise
                await recover_poisoned_connection(
                    signal=self._recovery_signal_from_decode_error(exc),
                    checkpoint=checkpoint,
                )
            except BaseException:
                updates_engine.restore(checkpoint)
                raise

        try:
            if initial_catch_up is not None:
                checkpoint, applied = initial_catch_up
                try:
                    await dispatch(checkpoint=checkpoint, applied=applied)
                    clear_circuit_after_success(
                        checkpoint=checkpoint,
                        applied=applied,
                        independently_healthy_live_input=False,
                    )
                except RpcDecodeError as exc:
                    updates_engine.restore(checkpoint)
                    if not exc.requires_reconnect:
                        raise
                    await recover_poisoned_connection(
                        signal=self._recovery_signal_from_decode_error(exc),
                        checkpoint=checkpoint,
                    )

            while True:
                try:
                    incoming = self._incoming
                    if incoming is None:
                        raise MtprotoClientError("MTProto receiver is not connected")
                    msg = await asyncio.wait_for(
                        incoming.get(),
                        timeout=_UPDATES_IDLE_RECOVERY_SECONDS,
                    )
                except asyncio.TimeoutError:
                    logger.info("No updates received for 15 minutes; fetching difference")
                    checkpoint = updates_engine.checkpoint()
                    await apply_and_dispatch_with_poison_recovery(
                        operation=updates_engine.recover,
                        checkpoint=checkpoint,
                    )
                    continue

                if isinstance(msg, ReceiverTerminated):
                    if isinstance(msg.error, RpcDecodeError) and msg.error.requires_reconnect:
                        checkpoint = updates_engine.checkpoint()
                        await recover_poisoned_connection(
                            signal=self._recovery_signal_from_decode_error(msg.error),
                            checkpoint=checkpoint,
                        )
                        continue
                    self._finish_updates(msg.error)
                    return

                checkpoint = updates_engine.checkpoint()
                if isinstance(msg, UpdatesRecoveryRequired):
                    logger.info(
                        "Updates recovery requested: %s",
                        msg.reason,
                    )
                    if msg.requires_reconnect:
                        await recover_poisoned_connection(
                            signal=msg,
                            checkpoint=checkpoint,
                        )
                    else:
                        await apply_and_dispatch_with_poison_recovery(
                            operation=updates_engine.recover,
                            checkpoint=checkpoint,
                        )
                else:
                    await apply_and_dispatch_with_poison_recovery(
                        operation=lambda: updates_engine.apply(msg.obj),
                        checkpoint=checkpoint,
                        independently_healthy_live_input=True,
                    )
        except asyncio.CancelledError:
            raise
        except BaseException as exc:
            self._finish_updates(exc)

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

    def _auth_key_id_hex(self) -> str | None:
        state = self._state
        if state is None:
            return None
        return int(state.auth_key_id).to_bytes(8, "little", signed=False).hex()

    def _clear_session_sidecars(self) -> None:
        for path in (self._entities_path(), self._updates_state_path()):
            if path is not None:
                path.unlink(missing_ok=True)

    def _clear_local_session_files(self) -> None:
        self._clear_session_sidecars()
        if self._session_path is not None:
            session = self._session_path.expanduser().resolve()
            parent = session.parent
            pointer_candidates = {
                parent / "current",
                parent / "current_bot",
                parent / "prod.current",
                parent / "prod.bot.current",
                parent.parent / "prod.current",
                parent.parent / "prod.bot.current",
            }
            for pointer in pointer_candidates:
                try:
                    raw_target = pointer.read_text(encoding="utf-8").strip()
                except (FileNotFoundError, OSError, UnicodeError):
                    continue
                target = Path(raw_target).expanduser()
                if not target.is_absolute():
                    target = (Path.cwd() / target).resolve()
                if target == session:
                    pointer.unlink(missing_ok=True)
            self._session_path.unlink(missing_ok=True)

    def _load_updates_state(self) -> UpdatesState | None:
        p = self._updates_state_path()
        if p is None or not p.exists():
            return None
        try:
            from telecraft.mtproto.updates.storage import (
                LegacyUpdatesStateMigrationRequired,
                UpdatesStateStorageError,
                load_updates_state_file,
            )

            auth_key_id = self._auth_key_id_hex()
            if auth_key_id is None:
                return None
            try:
                state = load_updates_state_file(
                    p,
                    expected_auth_key_id=auth_key_id,
                    allow_unbound_legacy=self._trust_legacy_updates_state,
                )
            except LegacyUpdatesStateMigrationRequired as exc:
                raise MtprotoClientError(
                    "Legacy updates checkpoint cannot be proven to belong to this account. "
                    "Delete the .updates.json sidecar to reset from current server state, "
                    "or explicitly pass trust_legacy_updates_state=True once to preserve "
                    "offline update continuity."
                ) from exc
            except UpdatesStateStorageError as current_auth_error:
                alias = self._updates_state_auth_key_id_alias
                if alias is None or alias == auth_key_id:
                    raise
                try:
                    state = load_updates_state_file(
                        p,
                        expected_auth_key_id=alias,
                        allow_unbound_legacy=self._trust_legacy_updates_state,
                    )
                except UpdatesStateStorageError:
                    raise current_auth_error
                logger.warning(
                    "Loading updates checkpoint through the previous-DC authorization alias: %s",
                    p,
                )
            if self._trust_legacy_updates_state:
                logger.warning(
                    "Trusting a legacy unbound updates checkpoint for one-time migration: %s",
                    p,
                )
            return state
        except MtprotoClientError:
            raise
        except Exception as exc:
            self.last_persistence_error = exc
            if self._strict_update_persistence:
                raise MtprotoClientError(
                    f"Updates checkpoint is invalid or unreadable: {p}. "
                    "Move/delete it explicitly to reset from the server's current state."
                ) from exc
            logger.warning(
                "Ignoring invalid updates checkpoint because strict_update_persistence=False: %s",
                p,
                exc_info=True,
            )
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

            auth_key_id = self._auth_key_id_hex()
            if auth_key_id is None:
                return
            save_updates_state_file(
                p,
                self._updates_engine.checkpoint(),
                auth_key_id=auth_key_id,
            )
            # The checkpoint is now bound to the current DC's auth key.  A
            # previous-DC alias retained in the session is no longer needed and
            # will be removed on the next session-file write.
            self._updates_state_auth_key_id_alias = None
            self.last_persistence_error = None
        except Exception as exc:
            self.last_persistence_error = exc
            logger.error("Failed to persist updates checkpoint: %s", p, exc_info=True)
            if self._strict_update_persistence:
                raise MtprotoClientError(f"Failed to persist updates checkpoint: {p}") from exc

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
        auth_key_id = self._auth_key_id_hex()
        self.entities = EntityCache(auth_key_id=auth_key_id)
        p = self._entities_path()
        if auth_key_id is None or p is None or not p.exists():
            return
        try:
            loaded = load_entity_cache_file(p)
            if loaded.auth_key_id != auth_key_id:
                return
            self.entities = loaded
        except Exception:
            # Entity lookup is an optimization, unlike an updates checkpoint.
            logger.warning("Ignoring invalid entity cache: %s", p, exc_info=True)

    def _persist_entities_cache(self, *, force: bool = False) -> None:
        p = self._entities_path()
        if p is None:
            return
        now = time.monotonic()
        if not force and (now - self._entities_last_save) < 2.0:
            return
        self._entities_last_save = now
        try:
            auth_key_id = self._auth_key_id_hex()
            if auth_key_id is None:
                return
            self.entities.auth_key_id = auth_key_id
            save_entity_cache_file(p, self.entities)
        except Exception:
            # Entity lookup is an optimization, unlike an updates checkpoint.
            logger.warning("Failed to persist entity cache: %s", p, exc_info=True)

    async def get_me(self, *, timeout: float = 20.0) -> Any:
        """
        Fetch current user and update entity cache.

        Returns the User object, or None if not logged in or got UserEmpty.
        """

        def _users_from_result(obj: Any) -> list[Any]:
            users_obj = obj if isinstance(obj, list) else getattr(obj, "users", [])
            return users_obj if isinstance(users_obj, list) else []

        res = await self.invoke_api(UsersGetUsers(id=[InputUserSelf()]), timeout=timeout)
        users = _users_from_result(res)
        # An empty users.getUsers result can occur for an unavailable/self identity;
        # fall back to the structured users.getFullUser response before returning None.
        if not users:
            full = await self.invoke_api(UsersGetFullUser(id=InputUserSelf()), timeout=timeout)
            users = _users_from_result(full)
        self.entities.ingest_users(users)
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
            self.entities.self_user_id = int(mid)
        self._persist_entities_cache()
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

    async def resolve_phone(
        self, phone: str, *, timeout: float = 20.0, force: bool = False
    ) -> Peer:
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
            if is_self_peer_ref(s):
                if self.self_user_id is None:
                    await self.get_me(timeout=timeout)
                if self.self_user_id is None:
                    raise MtprotoClientError("resolve_peer: cannot determine the current account")
                self.entities.self_user_id = int(self.self_user_id)
                return Peer.user(self.self_user_id)
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

    async def send_message_self(
        self,
        text: str,
        *,
        reply_to_msg_id: int | None = None,
        silent: bool = False,
        reply_markup: Any | None = None,
        timeout: float = 20.0,
    ) -> Any:
        """
        Minimal send message to self (no entity resolution needed).
        """
        from telecraft.tl.generated.types import InputPeerSelf

        return await self.send_message_peer(
            InputPeerSelf(),
            text,
            reply_to_msg_id=reply_to_msg_id,
            silent=silent,
            reply_markup=reply_markup,
            timeout=timeout,
        )

    async def send_message_chat(
        self,
        chat_id: int,
        text: str,
        *,
        reply_to_msg_id: int | None = None,
        silent: bool = False,
        reply_markup: Any | None = None,
        timeout: float = 20.0,
    ) -> Any:
        """
        Send a message to a basic group chat (InputPeerChat doesn't need access_hash).
        """
        from telecraft.tl.generated.types import InputPeerChat

        return await self.send_message_peer(
            InputPeerChat(chat_id=int(chat_id)),
            text,
            reply_to_msg_id=reply_to_msg_id,
            silent=silent,
            reply_markup=reply_markup,
            timeout=timeout,
        )

    async def send_message_user(
        self,
        user_id: int,
        text: str,
        *,
        reply_to_msg_id: int | None = None,
        silent: bool = False,
        reply_markup: Any | None = None,
        timeout: float = 20.0,
    ) -> Any:
        """
        Send a message to a user (requires access_hash in the entity cache).
        """
        try:
            peer = self.entities.input_peer_user(int(user_id))
        except EntityCacheError:
            await self._prime_entities_for_reply(want=Peer.user(int(user_id)), timeout=timeout)
            peer = self.entities.input_peer_user(int(user_id))
        return await self.send_message_peer(
            peer,
            text,
            reply_to_msg_id=reply_to_msg_id,
            silent=silent,
            reply_markup=reply_markup,
            timeout=timeout,
        )

    async def send_message_channel(
        self,
        channel_id: int,
        text: str,
        *,
        reply_to_msg_id: int | None = None,
        silent: bool = False,
        reply_markup: Any | None = None,
        timeout: float = 20.0,
    ) -> Any:
        """
        Send a message to a channel/supergroup (requires access_hash in the entity cache).
        """
        try:
            peer = self.entities.input_peer_channel(int(channel_id))
        except EntityCacheError:
            await self._prime_entities_for_reply(
                want=Peer.channel(int(channel_id)), timeout=timeout
            )
            peer = self.entities.input_peer_channel(int(channel_id))
        return await self.send_message_peer(
            peer,
            text,
            reply_to_msg_id=reply_to_msg_id,
            silent=silent,
            reply_markup=reply_markup,
            timeout=timeout,
        )

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
            reply_markup: Optional raw Telegram ReplyMarkup TL object
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
                poll_option=None,
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
                rich_message=None,
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
        - accepts Peer / ('user'|'chat'|'channel', id) / 'self' / 'me'
          / '@username' / '+phone' / cached int id
        - resolves to InputPeer and calls messages.sendMessage

        Args:
            peer: Target peer (can be self/me, Peer, tuple, @username, +phone,
                or cached int id)
            text: Message text
            reply_to_msg_id: Optional message ID to reply to
            silent: Send without notification
            reply_markup: Optional raw Telegram ReplyMarkup TL object
            timeout: RPC timeout in seconds
        """
        if is_self_peer_ref(peer):
            from telecraft.tl.generated.types import InputPeerSelf

            return await self.send_message_peer(
                InputPeerSelf(),
                text,
                reply_to_msg_id=reply_to_msg_id,
                silent=silent,
                reply_markup=reply_markup,
                timeout=timeout,
            )

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
                input_peer,
                text,
                reply_to_msg_id=reply_to_msg_id,
                silent=silent,
                reply_markup=reply_markup,
                timeout=timeout,
            )
        except RpcErrorException as e:
            if e.message == "PEER_ID_INVALID":
                await _refresh_peer_ref()
                input_peer = await _build_input_peer()
                return await self.send_message_peer(
                    input_peer,
                    text,
                    reply_to_msg_id=reply_to_msg_id,
                    silent=silent,
                    reply_markup=reply_markup,
                    timeout=timeout,
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
            InputPeerSelf,
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

        media: Any
        if as_photo:
            media = InputMediaUploadedPhoto(
                flags=0,
                spoiler=False,
                live_photo=False,
                file=input_file,
                stickers=None,
                ttl_seconds=None,
                video=None,
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
                poll_option=None,
            )

        if is_self_peer_ref(peer):
            input_peer = InputPeerSelf()
        else:
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
            InputPeerSelf,
            InputReplyToMessage,
            InputSingleMedia,
        )

        if len(paths) < 2:
            raise MtprotoClientError("send_album: need at least 2 files")
        if len(paths) > 10:
            raise MtprotoClientError("send_album: maximum 10 files")

        if captions is not None and len(captions) != len(paths):
            raise MtprotoClientError("send_album: captions must match paths length")

        if is_self_peer_ref(peer):
            input_peer = InputPeerSelf()
        else:
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

            media: Any
            if is_photo:
                media = InputMediaUploadedPhoto(
                    flags=0,
                    spoiler=False,
                    live_photo=False,
                    file=input_file,
                    stickers=None,
                    ttl_seconds=None,
                    video=None,
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
                monoforum_peer_id=None,
                todo_item_id=None,
                poll_option=None,
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
                rich_message=None,
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
        filter: Any | None = None,
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
            filter: Raw InputMessagesFilter TL object (defaults to no filtering)
            offset_id: Offset message ID for pagination
            min_date: Minimum message date (Unix timestamp)
            max_date: Maximum message date (Unix timestamp)
            timeout: RPC timeout in seconds

        Returns:
            List of Message objects
        """
        from telecraft.tl.generated.types import (
            InputMessagesFilterEmpty,
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
                flags=1 if from_input_peer is not None else 0,
                peer=input_peer,
                q=query,
                from_id=from_input_peer,
                saved_peer_id=None,
                saved_reaction=None,
                top_msg_id=None,
                filter=filter if filter is not None else InputMessagesFilterEmpty(),
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
        _return_users: bool = False,
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
            ChannelParticipantsAdmins,
            ChannelParticipantsBanned,
            ChannelParticipantsBots,
            ChannelParticipantsKicked,
            ChannelParticipantsRecent,
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
            users_by_id = {
                int(user_id): user
                for user in users
                if (user_id := getattr(user, "id", None)) is not None
            }

            participants = cast(list[Any], getattr(res, "participants", []))
            if not participants:
                break

            for p in participants:
                if limit is not None and total_yielded >= limit:
                    return
                if _return_users:
                    participant_user_id = getattr(p, "user_id", None)
                    if participant_user_id is None:
                        continue
                    user = users_by_id.get(int(participant_user_id))
                    if user is None:
                        logger.warning(
                            "Telegram omitted User for channel participant user_id=%s",
                            participant_user_id,
                        )
                        continue
                    yield user
                else:
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
            SendMessageCancelAction,
            SendMessageChooseStickerAction,
            SendMessageGamePlayAction,
            SendMessageRecordAudioAction,
            SendMessageRecordVideoAction,
            SendMessageTypingAction,
            SendMessageUploadDocumentAction,
            SendMessageUploadPhotoAction,
            SendMessageUploadVideoAction,
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

        normalized_photo_ids: list[tuple[int, int]]
        if isinstance(photo_ids, tuple) and len(photo_ids) == 2 and isinstance(photo_ids[0], int):
            # Single photo
            normalized_photo_ids = [photo_ids]
        else:
            normalized_photo_ids = list(photo_ids)

        input_photos = [
            InputPhoto(id=pid, access_hash=ahash, file_reference=b"")
            for pid, ahash in normalized_photo_ids
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
            await self._prime_entities_for_reply(
                want=Peer.channel(int(ch.peer_id)), timeout=timeout
            )
            input_channel = self.entities.input_channel(int(ch.peer_id))

        u = await self.resolve_peer(user, timeout=timeout)
        if u.peer_type != "user":
            raise MtprotoClientError(f"edit_admin: user must be a user, got {u.peer_type}")
        try:
            input_user: InputUser | InputUserSelf = self.entities.input_user(int(u.peer_id))
        except EntityCacheError:
            await self._prime_entities_for_reply(want=Peer.user(int(u.peer_id)), timeout=timeout)
            input_user = self.entities.input_user(int(u.peer_id))

        res = await self.invoke_api(
            ChannelsEditAdmin(
                flags=1 if rank else 0,
                channel=input_channel,
                user_id=input_user,
                admin_rights=admin_rights,
                rank=rank or None,
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
            raise MtprotoClientError(f"edit_banned: channel must be a channel, got {ch.peer_type}")
        try:
            input_channel = self.entities.input_channel(int(ch.peer_id))
        except EntityCacheError:
            await self._prime_entities_for_reply(
                want=Peer.channel(int(ch.peer_id)), timeout=timeout
            )
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
            raise MtprotoClientError(
                f"get_chat_member: channel must be a channel, got {ch.peer_type}"
            )

        try:
            input_channel = self.entities.input_channel(int(ch.peer_id))
        except EntityCacheError:
            await self._prime_entities_for_reply(
                want=Peer.channel(int(ch.peer_id)), timeout=timeout
            )
            input_channel = self.entities.input_channel(int(ch.peer_id))

        u = await self.resolve_peer(user, timeout=timeout)
        if u.peer_type != "user":
            raise MtprotoClientError(f"get_chat_member: user must be a user, got {u.peer_type}")

        participant = Peer.user(int(u.peer_id))
        try:
            input_participant = self.entities.input_peer(participant)
        except EntityCacheError:
            await self._prime_entities_for_reply(want=participant, timeout=timeout)
            input_participant = self.entities.input_peer(participant)

        res = await self.invoke_api(
            ChannelsGetParticipant(channel=input_channel, participant=input_participant),
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
                raise MtprotoClientError(
                    f"create_group: all members must be users, got {u.peer_type}"
                )
            try:
                input_user = self.entities.input_user(int(u.peer_id))
            except EntityCacheError:
                await self._prime_entities_for_reply(
                    want=Peer.user(int(u.peer_id)), timeout=timeout
                )
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
                await self._prime_entities_for_reply(
                    want=Peer.channel(int(p.peer_id)), timeout=timeout
                )
                input_channel = self.entities.input_channel(int(p.peer_id))

            res = await self.invoke_api(
                ChannelsEditTitle(channel=input_channel, title=title),
                timeout=timeout,
            )
        else:
            raise MtprotoClientError(
                f"set_chat_title: peer must be a group/channel, got {p.peer_type}"
            )

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
                await self._prime_entities_for_reply(
                    want=Peer.channel(int(p.peer_id)), timeout=timeout
                )
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

        from telecraft.client.media import _tl_bool

        res = await self.invoke_api(
            MessagesUpdateDialogFilter(
                flags=1,  # filter present
                id=folder_id,
                filter=dialog_filter,
            ),
            timeout=timeout,
        )
        return _tl_bool(res) is True

    async def delete_folder(self, folder_id: int, *, timeout: float = 20.0) -> bool:
        """
        Delete a chat folder.

        Args:
            folder_id: The folder ID to delete

        Returns:
            True if successful
        """
        from telecraft.client.media import _tl_bool
        from telecraft.tl.generated.functions import MessagesUpdateDialogFilter

        res = await self.invoke_api(
            MessagesUpdateDialogFilter(
                flags=0,  # no filter = delete
                id=folder_id,
                filter=None,
            ),
            timeout=timeout,
        )
        return _tl_bool(res) is True

    async def reorder_folders(self, folder_ids: list[int], *, timeout: float = 20.0) -> bool:
        """
        Reorder chat folders.

        Args:
            folder_ids: List of folder IDs in desired order

        Returns:
            True if successful
        """
        from telecraft.client.media import _tl_bool
        from telecraft.tl.generated.functions import MessagesUpdateDialogFiltersOrder

        res = await self.invoke_api(
            MessagesUpdateDialogFiltersOrder(order=folder_ids),
            timeout=timeout,
        )
        return _tl_bool(res) is True

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
                monoforum_peer_id=None,
                todo_item_id=None,
                poll_option=None,
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
                monoforum_peer_id=None,
                todo_item_id=None,
                poll_option=None,
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
                rich_message=None,
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
                monoforum_peer_id=None,
                todo_item_id=None,
                poll_option=None,
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
        from telecraft.tl.generated.functions import MessagesGetStickerSet
        from telecraft.tl.generated.types import InputStickerSetShortName

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
                monoforum_peer_id=None,
                todo_item_id=None,
                poll_option=None,
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
                f"send_dice: unsupported emoji '{emoji}'. Supported: {', '.join(SUPPORTED_DICE)}"
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
                monoforum_peer_id=None,
                todo_item_id=None,
                poll_option=None,
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
                monoforum_peer_id=None,
                todo_item_id=None,
                poll_option=None,
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
                monoforum_peer_id=None,
                todo_item_id=None,
                poll_option=None,
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
                    flags=0,
                    text=TextWithEntities(text=opt, entities=[]),
                    option=bytes([i]),  # option identifier
                    media=None,
                    added_by=None,
                    date=None,
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
            open_answers=None,
            revoting_disabled=None,
            shuffle_answers=None,
            hide_results_until_close=None,
            creator=None,
            subscribers_only=None,
            question=TextWithEntities(text=question, entities=[]),
            answers=answers,
            close_period=close_period,
            close_date=close_date,
            countries_iso2=None,
            hash=0,
        )

        media = InputMediaPoll(
            flags=0,
            poll=poll,
            correct_answers=None,
            attached_media=None,
            solution=None,
            solution_entities=None,
            solution_media=None,
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
                monoforum_peer_id=None,
                todo_item_id=None,
                poll_option=None,
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
            raise MtprotoClientError(f"send_quiz: correct_option must be 0-{len(options) - 1}")

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
                    flags=0,
                    text=TextWithEntities(text=opt, entities=[]),
                    option=bytes([i]),
                    media=None,
                    added_by=None,
                    date=None,
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
            open_answers=None,
            revoting_disabled=None,
            shuffle_answers=None,
            hide_results_until_close=None,
            creator=None,
            subscribers_only=None,
            question=TextWithEntities(text=question, entities=[]),
            answers=answers,
            close_period=close_period,
            close_date=None,
            countries_iso2=None,
            hash=0,
        )

        # Build media flags
        media_flags = 1  # flags.0 = correct_answers
        if explanation:
            media_flags |= 2  # flags.1 = solution

        media = InputMediaPoll(
            flags=media_flags,
            poll=poll,
            correct_answers=[int(correct_option)],
            attached_media=None,
            solution=explanation,
            solution_entities=[] if explanation else None,
            solution_media=None,
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
                monoforum_peer_id=None,
                todo_item_id=None,
                poll_option=None,
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
        from telecraft.tl.generated.functions import (
            ChannelsGetMessages,
            MessagesEditMessage,
            MessagesGetMessages,
        )
        from telecraft.tl.generated.types import (
            InputMediaPoll,
            InputMessageId,
            MessageMediaPoll,
            Poll,
        )

        p = await self.resolve_peer(peer, timeout=timeout)

        try:
            input_peer = self.entities.input_peer(p)
        except EntityCacheError:
            await self._prime_entities_for_reply(want=p, timeout=timeout)
            input_peer = self.entities.input_peer(p)

        message_ref = InputMessageId(id=int(msg_id))
        if p.peer_type == "channel":
            try:
                input_channel = self.entities.input_channel(int(p.peer_id))
            except EntityCacheError:
                await self._prime_entities_for_reply(want=p, timeout=timeout)
                input_channel = self.entities.input_channel(int(p.peer_id))
            current = await self.invoke_api(
                ChannelsGetMessages(channel=input_channel, id=[message_ref]),
                timeout=timeout,
            )
        else:
            current = await self.invoke_api(MessagesGetMessages(id=[message_ref]), timeout=timeout)

        self._ingest_from_updates_result(current)
        messages = getattr(current, "messages", None)
        message = (
            next(
                (
                    candidate
                    for candidate in messages
                    if int(getattr(candidate, "id", -1)) == int(msg_id)
                ),
                None,
            )
            if isinstance(messages, list)
            else None
        )
        media = getattr(message, "media", None)
        if not isinstance(media, MessageMediaPoll):
            raise MtprotoClientError(
                f"close_poll: message {msg_id} does not contain an editable poll"
            )
        poll = cast(Poll, media.poll)
        closed_poll = replace(
            poll,
            flags=int(cast(int, poll.flags)) | 1,
            closed=True,
        )

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
                    poll=closed_poll,
                    correct_answers=None,
                    attached_media=None,
                    solution=None,
                    solution_entities=None,
                    solution_media=None,
                ),
                reply_markup=None,
                entities=None,
                schedule_date=None,
                schedule_repeat_period=None,
                quick_reply_shortcut_id=None,
                rich_message=None,
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
            MessagesGetPollResults(peer=input_peer, msg_id=msg_id, poll_hash=0),
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
        - supergroups/channels (peer_type='channel'):
          channels.inviteToChannel(channel, users=[user])
        """
        g = await self.resolve_peer(group, timeout=timeout)
        u = await self.resolve_peer(user, timeout=timeout)
        if u.peer_type != "user":
            raise MtprotoClientError(f"add_user_to_group: user must be a user, got {u.peer_type}")

        async def _build_input_user() -> InputUser | InputUserSelf:
            try:
                return self.entities.input_user(int(u.peer_id))
            except EntityCacheError:
                await self._prime_entities_for_reply(
                    want=Peer.user(int(u.peer_id)), timeout=timeout
                )
                return self.entities.input_user(int(u.peer_id))

        async def _refresh_user_ref() -> None:
            """
            Best-effort refresh when Telegram returns USER_ID_INVALID/USER_INVALID.

            Common case: stale username/phone -> user_id mapping in the persisted EntityCache.
            """
            nonlocal u
            # If we have a username/phone ref, force a network resolve
            # to refresh user_id/access_hash.
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
            # Otherwise, just try priming (may refresh access_hash
            # if the user is present in dialogs).
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
                await self._prime_entities_for_reply(
                    want=Peer.channel(int(g.peer_id)), timeout=timeout
                )
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
        async for member in self.iter_participants(
            group,
            limit=limit,
            timeout=timeout,
            _return_users=True,
        ):
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
        exclude_self: bool = True,
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
            exclude_self: Skip the current account (default True)
            timeout: RPC timeout per operation
            on_error: How to handle errors ("skip", "raise", "collect")

        Returns:
            Dict with transfer statistics
        """
        # Get members from source group
        members = await self.get_group_members(from_group, limit=limit, timeout=timeout)

        admin_ids: set[int] = set()
        if exclude_admins:
            async for participant in self.iter_participants(
                from_group,
                filter_type="admins",
                timeout=timeout,
            ):
                admin_id = getattr(participant, "user_id", None)
                if admin_id is not None:
                    admin_ids.add(int(admin_id))

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

            if exclude_admins and int(user_id) in admin_ids:
                skipped.append((int(user_id), "admin"))
                continue

            # Check if self
            if exclude_self and user_id == self.self_user_id:
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
                raise MtprotoClientError(
                    f"remove_user_from_group: user must be a user, got {u.peer_type}"
                )

            try:
                input_user = self.entities.input_user(int(u.peer_id))
            except EntityCacheError:
                await self._prime_entities_for_reply(
                    want=Peer.user(int(u.peer_id)), timeout=timeout
                )
                input_user = self.entities.input_user(int(u.peer_id))

            from telecraft.tl.generated.functions import MessagesDeleteChatUser

            res = await self.invoke_api(
                MessagesDeleteChatUser(
                    flags=0, revoke_history=False, chat_id=int(g.peer_id), user_id=input_user
                ),
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

    async def _migrate_primary_dc(
        self,
        dc_id: int,
        *,
        kind: str,
        timeout: float,
    ) -> None:
        """Move this client's primary MTProto connection to a server-directed DC."""

        target_dc = int(dc_id)
        if target_dc <= 0:
            raise MtprotoClientError(f"Invalid migration DC: {dc_id!r}")
        if not math.isfinite(timeout) or timeout <= 0:
            raise MtprotoClientError(f"Timed out migrating {kind} request to DC {target_dc}")
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout

        def remaining() -> float:
            value = deadline - loop.time()
            if value <= 0:
                raise asyncio.TimeoutError
            return value

        try:
            # The global order for connection mutation is lifecycle ->
            # migration -> invoke condition.  Lifecycle callers such as
            # start_updates/log_out re-enter this serializer in the same task.
            async with self._lifecycle_serialized(timeout=remaining()):
                await asyncio.wait_for(
                    self._migration_lock.acquire(),
                    timeout=remaining(),
                )
                migration_announced = False
                try:
                    if target_dc == int(self._dc_id):
                        return

                    async with self._invoke_condition:
                        self._migration_in_progress = True
                        migration_announced = True
                    try:
                        async with self._invoke_condition:
                            while self._active_invocations:
                                await asyncio.wait_for(
                                    self._invoke_condition.wait(),
                                    timeout=remaining(),
                                )
                        await self._perform_primary_dc_migration(
                            target_dc,
                            kind=kind,
                            timeout=remaining(),
                        )
                    finally:
                        if migration_announced:
                            async with self._invoke_condition:
                                self._migration_in_progress = False
                                self._invoke_condition.notify_all()
                finally:
                    self._migration_lock.release()
        except asyncio.TimeoutError as exc:
            raise MtprotoClientError(
                f"Timed out migrating {kind} request to DC {target_dc}"
            ) from exc

    async def _perform_primary_dc_migration(
        self,
        target_dc: int,
        *,
        kind: str,
        timeout: float,
    ) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout

        def remaining() -> float:
            value = deadline - loop.time()
            if value <= 0:
                raise asyncio.TimeoutError
            return value

        async with self._lifecycle_serialized(timeout=remaining()):
            old_sender = self._sender
            old_transport = self._transport
            old_incoming = self._incoming
            if old_sender is None or old_transport is None or self._state is None:
                raise MtprotoClientError("Cannot migrate a disconnected client")
            if self._init is None:
                raise MtprotoClientError(
                    "ClientInit(api_id=...) is required for automatic DC migration"
                )
            old_auth_key_id = self._auth_key_id_hex()
            old_updates_auth_alias = self._updates_state_auth_key_id_alias

            target_host, target_port = self._endpoint_for_dc(target_dc)
            candidate = MtprotoClient(
                network=self._network,
                dc_id=target_dc,
                host=target_host,
                port=target_port,
                framing=self._framing_name,
                session_path=None,
                init=self._init,
                trust_legacy_updates_state=self._trust_legacy_updates_state,
                strict_update_persistence=self._strict_update_persistence,
                flood_wait_config=self._flood_wait_config,
                lock_session=False,
            )
            adopted = False
            failure: BaseException | None = None
            candidate_operation_tasks: set[asyncio.Task[Any]] = set()
            try:
                connect_task = self._track_background_task(
                    candidate.connect(timeout=remaining()),
                    label=f"migration-candidate-connect-dc{target_dc}",
                )
                candidate_operation_tasks.add(connect_task)
                await self._await_task_hard_bounded(
                    connect_task,
                    timeout=remaining(),
                )

                exported: Any | None = None
                try:
                    export_task = self._track_background_task(
                        old_sender.invoke_tl(
                            AuthExportAuthorization(dc_id=target_dc),
                            timeout=remaining(),
                            flood_wait_config=self._flood_wait_config,
                        ),
                        label=f"migration-export-authorization-dc{target_dc}",
                    )
                    exported = await self._await_task_hard_bounded(
                        export_task,
                        timeout=remaining(),
                    )
                except RpcErrorException as exc:
                    # PHONE/NETWORK migrations can happen before a user or bot
                    # has authorized this fresh auth key.  USER_MIGRATE, on the
                    # other hand, promises an existing authorization and must not
                    # silently downgrade to an unauthenticated connection.
                    unauthenticated_errors = {
                        "AUTH_KEY_UNREGISTERED",
                        "SESSION_REVOKED",
                        "USER_DEACTIVATED",
                        "USER_DEACTIVATED_BAN",
                    }
                    if exc.message not in unauthenticated_errors or kind == "USER":
                        raise

                if exported is not None:
                    exp_id = getattr(exported, "id", None)
                    exp_bytes = getattr(exported, "bytes", None)
                    if not isinstance(exp_id, int) or not isinstance(exp_bytes, (bytes, bytearray)):
                        raise MtprotoClientError(
                            "Telegram returned an invalid auth.exportAuthorization payload"
                        )
                    import_task = self._track_background_task(
                        candidate.invoke_api(
                            AuthImportAuthorization(id=exp_id, bytes=bytes(exp_bytes)),
                            timeout=remaining(),
                        ),
                        label=f"migration-candidate-import-dc{target_dc}",
                    )
                    candidate_operation_tasks.add(import_task)
                    await self._await_task_hard_bounded(
                        import_task,
                        timeout=remaining(),
                    )

                new_transport = candidate._transport
                new_sender = candidate._sender
                new_state = candidate._state
                new_msg_id_gen = candidate._msg_id_gen
                new_incoming = candidate._incoming
                if (
                    new_transport is None
                    or new_sender is None
                    or new_state is None
                    or new_msg_id_gen is None
                    or new_incoming is None
                ):
                    raise MtprotoClientError(
                        "DC migration candidate did not establish a complete connection"
                    )
                new_auth_key_id = (
                    int(new_state.auth_key_id)
                    .to_bytes(
                        8,
                        "little",
                        signed=False,
                    )
                    .hex()
                )
                new_framing_name = candidate._framing_name
                new_config = candidate.config
                new_did_init_connection = candidate._did_init_connection
                candidate_dc_endpoints = dict(candidate._dc_endpoints)

                # Inspect the durable checkpoint before adoption.  Everything
                # from the first self-assignment through spawning cleanup owners
                # below is deliberately synchronous: cancellation cannot leave
                # an old resource detached and unowned.
                migration_persistence_error: BaseException | None = None
                checkpoint_path = self._updates_state_path()
                checkpoint_auth_key_id: str | None = None
                if checkpoint_path is not None and checkpoint_path.exists():
                    try:
                        from telecraft.mtproto.updates.storage import (
                            inspect_updates_state_file_auth_key_id,
                        )

                        checkpoint_auth_key_id = inspect_updates_state_file_auth_key_id(
                            checkpoint_path
                        )
                        allowed_bindings = {
                            value
                            for value in (old_auth_key_id, old_updates_auth_alias)
                            if value is not None
                        }
                        if (
                            checkpoint_auth_key_id is not None
                            and checkpoint_auth_key_id not in allowed_bindings
                        ):
                            raise MtprotoClientError(
                                "Updates checkpoint authorization changed during DC migration"
                            )
                    except Exception as exc:  # noqa: BLE001
                        if self._strict_update_persistence:
                            migration_persistence_error = MtprotoClientError(
                                f"Cannot safely migrate updates checkpoint: {checkpoint_path}"
                            )
                            migration_persistence_error.__cause__ = exc
                        else:
                            logger.warning(
                                "Ignoring invalid updates checkpoint during DC migration because "
                                "strict_update_persistence=False: %s",
                                checkpoint_path,
                                exc_info=True,
                            )
                            checkpoint_auth_key_id = None

                new_updates_auth_alias = (
                    (old_updates_auth_alias or old_auth_key_id)
                    if migration_persistence_error is not None
                    else (
                        checkpoint_auth_key_id
                        if checkpoint_auth_key_id is not None
                        and checkpoint_auth_key_id != new_auth_key_id
                        else None
                    )
                )

                # Wake an update loop currently blocked on the old queue.  Its
                # next recovery invocation uses the newly adopted sender.
                if old_incoming is not None:
                    old_sender._forward_incoming(  # noqa: SLF001 - same protocol layer
                        UpdatesRecoveryRequired(reason="dc_migration")
                    )

                stale_children = list(self._media_clients.values())
                cleanup_resources = [*stale_children, old_sender, old_transport]
                # Prepare non-resource state before the connection ownership
                # hand-off so the commit below contains only non-awaiting plain
                # assignments.
                self._dc_endpoints.update(candidate_dc_endpoints)
                self.entities.auth_key_id = new_auth_key_id
                for cleanup_resource in cleanup_resources:
                    self._retain_deferred_cleanup_resource(cleanup_resource)

                self._transport = new_transport
                self._sender = new_sender
                self._state = new_state
                self._msg_id_gen = new_msg_id_gen
                self._incoming = new_incoming
                self._dc_id = target_dc
                self._host = target_host
                self._port = target_port
                self._host_is_explicit = False
                self._framing_name = new_framing_name
                self.config = new_config
                self._did_init_connection = new_did_init_connection
                self._updates_state_auth_key_id_alias = new_updates_auth_alias

                # Transfer ownership before candidate cleanup can close the new
                # connection.
                candidate._transport = None
                candidate._sender = None
                candidate._state = None
                candidate._msg_id_gen = None
                candidate._incoming = None
                candidate.config = None
                adopted = True

                cleanup_tasks = {
                    self._spawn_resource_cleanup(
                        child,
                        label=f"migration-stale-child-dc{target_dc}-{index}",
                    )
                    for index, child in enumerate(stale_children)
                }
                cleanup_tasks.add(
                    self._spawn_resource_cleanup(
                        old_sender,
                        label=f"migration-old-sender-dc{target_dc}",
                    )
                )
                cleanup_tasks.add(
                    self._spawn_resource_cleanup(
                        old_transport,
                        label=f"migration-old-transport-dc{target_dc}",
                    )
                )
                self._media_clients.clear()

                persist_task: asyncio.Task[Any] | None = None
                if migration_persistence_error is None:
                    persist_task = self._track_background_task(
                        self._persist_session(),
                        label=f"migration-persist-session-dc{target_dc}",
                    )

                if persist_task is not None:
                    try:
                        await self._await_task_hard_bounded(
                            persist_task,
                            timeout=remaining(),
                        )
                    except asyncio.TimeoutError:
                        raise
                    except Exception as exc:  # cancellation must propagate
                        migration_persistence_error = exc

                done, pending = await asyncio.wait(
                    cleanup_tasks,
                    timeout=remaining(),
                )
                for cleanup_task in done:
                    try:
                        cleanup_task.result()
                    except BaseException:
                        logger.warning(
                            "Failed deferred migration cleanup task %s",
                            cleanup_task.get_name(),
                            exc_info=True,
                        )
                if pending:
                    raise asyncio.TimeoutError
                if migration_persistence_error is not None:
                    raise migration_persistence_error
                logger.info("Migrated primary MTProto connection to DC %d (%s)", target_dc, kind)
            except BaseException as exc:
                failure = exc
                raise
            finally:
                if not adopted:
                    self._retain_deferred_cleanup_resource(candidate)

                    async def close_unsuccessful_candidate() -> None:
                        try:
                            if candidate_operation_tasks:
                                await asyncio.gather(
                                    *candidate_operation_tasks,
                                    return_exceptions=True,
                                )
                            await candidate.close()
                        except BaseException:
                            raise
                        else:
                            self._release_deferred_cleanup_resource(candidate)

                    candidate_cleanup_task = self._track_background_task(
                        close_unsuccessful_candidate(),
                        label=f"migration-unsuccessful-candidate-dc{target_dc}",
                    )
                    self._deferred_cleanup_task_resources[candidate_cleanup_task] = candidate
                    if not isinstance(failure, asyncio.CancelledError):
                        try:
                            await self._await_task_hard_bounded(
                                candidate_cleanup_task,
                                timeout=remaining(),
                            )
                        except asyncio.TimeoutError:
                            pass
                        except BaseException:
                            logger.warning(
                                "Failed to close unsuccessful DC migration candidate",
                                exc_info=True,
                            )

    async def _client_for_dc(self, dc_id: int, *, timeout: float = 20.0) -> MtprotoClient:
        """
        Best-effort cross-DC helper for media downloads:
        - connect to dc_id
        - import authorization using auth.exportAuthorization/auth.importAuthorization
        """
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        if int(dc_id) == int(self._dc_id):
            return self
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout

        def remaining() -> float:
            value = deadline - loop.time()
            if value <= 0:
                raise MtprotoClientError(f"Timed out creating cross-DC client for DC {int(dc_id)}")
            return value

        # Share the lifecycle lock with close(): this both deduplicates concurrent
        # creators and prevents a newly connected child from escaping teardown.
        lifecycle_task = asyncio.current_task()
        if lifecycle_task is None:
            raise RuntimeError("Cross-DC client creation requires an asyncio task")
        lifecycle_reentrant = self._lifecycle_owner is lifecycle_task
        if lifecycle_reentrant:
            self._lifecycle_depth += 1
        else:
            try:
                await asyncio.wait_for(self._lifecycle_lock.acquire(), timeout=remaining())
            except asyncio.TimeoutError as exc:
                raise MtprotoClientError(
                    f"Timed out creating cross-DC client for DC {int(dc_id)}"
                ) from exc
            self._lifecycle_owner = lifecycle_task
            self._lifecycle_depth = 1
        try:
            existing = self._media_clients.get(int(dc_id))
            if existing is not None and existing.is_connected:
                return existing
            if existing is not None:
                # An unhealthy child may still own a transport or receiver task.
                # Remove it before awaiting cleanup so it cannot be returned or
                # overwritten without releasing those resources.
                self._media_clients.pop(int(dc_id), None)
                try:
                    await asyncio.wait_for(existing.close(), timeout=remaining())
                except asyncio.CancelledError:
                    raise
                except asyncio.TimeoutError:
                    logger.warning(
                        "Timed out closing unhealthy cross-DC client dc_id=%s",
                        dc_id,
                    )
                except BaseException:
                    logger.warning(
                        "Failed to close unhealthy cross-DC client dc_id=%s",
                        dc_id,
                        exc_info=True,
                    )

            if not self.is_connected:
                raise MtprotoClientError("Not connected")
            if self._init is None:
                raise MtprotoClientError(
                    "ClientInit(api_id=...) is required for cross-DC operations"
                )
            sender = self._sender
            if sender is None:
                raise MtprotoClientError("Not connected")

            host, port = self._endpoint_for_dc(int(dc_id))
            c = MtprotoClient(
                network=self._network,
                dc_id=int(dc_id),
                host=host,
                port=port,
                framing=self._framing_name,
                init=self._init,
                session_path=None,
                strict_update_persistence=self._strict_update_persistence,
                flood_wait_config=self._flood_wait_config,
                lock_session=False,
            )
            try:
                connect_timeout = remaining()
                await asyncio.wait_for(
                    c.connect(timeout=connect_timeout),
                    timeout=connect_timeout,
                )
                # Use the sender directly while holding lifecycle serialization. Calling
                # self.invoke_api here could react to USER_MIGRATE by trying to
                # acquire this same lock and deadlock the file-transfer path.
                exported = await sender.invoke_tl(
                    AuthExportAuthorization(dc_id=int(dc_id)),
                    timeout=remaining(),
                    flood_wait_config=self._flood_wait_config,
                )
                exp_id = getattr(exported, "id", None)
                exp_bytes = getattr(exported, "bytes", None)
                if not isinstance(exp_id, int) or not isinstance(exp_bytes, (bytes, bytearray)):
                    raise MtprotoClientError(
                        f"Unexpected auth.exportAuthorization result: {type(exported).__name__}"
                    )
                import_timeout = remaining()
                await asyncio.wait_for(
                    c.invoke_api(
                        AuthImportAuthorization(id=int(exp_id), bytes=bytes(exp_bytes)),
                        timeout=import_timeout,
                    ),
                    timeout=import_timeout,
                )
            except BaseException:
                try:
                    await c.close()
                except BaseException:
                    pass
                raise

            self._media_clients[int(dc_id)] = c
            return c
        except asyncio.TimeoutError as exc:
            raise MtprotoClientError(
                f"Timed out creating cross-DC client for DC {int(dc_id)}"
            ) from exc
        finally:
            if lifecycle_reentrant:
                self._lifecycle_depth -= 1
            else:
                if self._lifecycle_owner is not lifecycle_task or self._lifecycle_depth != 1:
                    raise RuntimeError("Lifecycle serialization ownership was corrupted")
                self._lifecycle_depth = 0
                self._lifecycle_owner = None
                self._lifecycle_lock.release()

    async def download_media(
        self,
        message_or_event: Any,
        *,
        dest: str | Path | None = None,
        timeout: float = 20.0,
    ) -> Path | bytes | None:
        """
        Download photo/document media from a TL message or MessageEvent.

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
            download_via_get_file_to_path,
            ensure_dest_path,
            extract_media,
            write_download_bytes,
        )

        m = extract_media(message_or_event)
        if m is None:
            return None

        try:
            out_path = ensure_dest_path(dest, file_name=m.file_name) if dest is not None else None
        except MediaError as e:
            raise MtprotoClientError(str(e)) from e

        # Check for cached bytes (small photos are sometimes embedded)
        if isinstance(m, ExtractedMediaWithCache) and m.cached_bytes:
            data = m.cached_bytes
            if out_path is not None:
                return write_download_bytes(out_path, data)
        else:
            try:
                c = await self._client_for_dc(int(m.dc_id), timeout=timeout)
                if out_path is not None:
                    return await download_via_get_file_to_path(
                        invoke_api=c.invoke_api,
                        location=m.location,
                        timeout=timeout,
                        path=out_path,
                        expected_size=m.size,
                    )
                data = await download_via_get_file(
                    invoke_api=c.invoke_api,
                    location=m.location,
                    timeout=timeout,
                    expected_size=m.size,
                )
            except MediaError as e:
                raise MtprotoClientError(str(e)) from e

        if out_path is None:
            return data
        return write_download_bytes(out_path, data)

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
            MessagesDialogsNotModified,
            MessagesDialogsSlice,
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
                        p = peer_from_tl_peer(last_dialog_peer)
                        if p is not None:
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
            InputPeerSelf,
            MessagesChannelMessages,
            MessagesMessages,
            MessagesMessagesSlice,
        )

        if is_self_peer_ref(peer):
            input_peer = InputPeerSelf()
        else:
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

            if not isinstance(
                res, (MessagesMessages, MessagesMessagesSlice, MessagesChannelMessages)
            ):
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
        Best-effort wrapper around messages.getHistory that also ingests
        users/chats into EntityCache.
        """
        from telecraft.tl.generated.types import (
            InputPeerSelf,
            MessagesChannelMessages,
            MessagesMessages,
            MessagesMessagesSlice,
        )

        if is_self_peer_ref(peer):
            input_peer = InputPeerSelf()
        else:
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
        if isinstance(res, (MessagesMessages, MessagesMessagesSlice, MessagesChannelMessages)):
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
            updates_state_auth_key_id_alias=self._updates_state_auth_key_id_alias,
        )
        save_session_file(self._session_path, sess)
