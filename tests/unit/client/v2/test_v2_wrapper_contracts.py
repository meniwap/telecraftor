from __future__ import annotations

import asyncio
import inspect
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from telecraft.client import (
    ChatlistRef,
    Client,
    DocumentRef,
    FolderAssignment,
    GiftRef,
    GroupCallRef,
    InvoiceRef,
    NotifyTarget,
    StickerSetRef,
    TakeoutScopes,
)

MATRIX_PATH = Path("tests/meta/v2_method_matrix.yaml")
UNIT_SCENARIOS = {
    "delegates_to_raw",
    "passes_timeout",
    "forwards_args",
    "returns_expected_shape",
    "handles_rpc_error",
}
DEFAULT_TIMEOUT = 9.5
ASYNC_ITER_METHODS = {
    ("messages", "iter_dialogs"),
    ("messages", "iter_messages"),
}
VOID_METHODS = {
    ("client", "close"),
    ("client", "connect"),
    ("peers", "prime"),
    ("updates", "start"),
    ("updates", "stop"),
}
METHOD_PARAM_OVERRIDES: dict[tuple[str, str, str], Any] = {
    ("polls", "vote", "options"): [0],
    ("profile", "delete_photos", "photo_ids"): [(1, 2)],
    ("media", "send_sticker", "sticker_file_reference"): b"ref",
    ("messages.sponsored", "view", "random_id"): b"rid",
    ("messages.sponsored", "click", "random_id"): b"rid",
    ("messages.sponsored", "report", "random_id"): b"rid",
}
OPTIONAL_REQUIRED_PARAMS: dict[tuple[str, str], set[str]] = {
    ("stars.transactions", "by_id"): {"tx_ids"},
}


class DummyRpcError(RuntimeError):
    pass


@dataclass(slots=True)
class RawCall:
    name: str
    args: tuple[Any, ...]
    kwargs: dict[str, Any]


class _Entities:
    def input_channel(self, peer_id: int) -> dict[str, int]:
        return {"input_channel": int(peer_id)}

    def input_user(self, user_id: int) -> dict[str, int]:
        return {"input_user": int(user_id)}

    def input_peer(self, resolved: Any) -> dict[str, Any]:
        return {"input_peer": resolved}


class SpyRaw:
    def __init__(self) -> None:
        self.calls: list[RawCall] = []
        self.raise_on: set[str] = set()
        self.is_connected = False
        self.entities = _Entities()

    def _record(self, name: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
        self.calls.append(RawCall(name=name, args=args, kwargs=dict(kwargs)))
        if name in self.raise_on:
            raise DummyRpcError(name)

    async def connect(self, *, timeout: float = 30.0) -> None:
        self._record("connect", (), {"timeout": timeout})
        self.is_connected = True

    async def close(self) -> None:
        self._record("close", (), {})
        self.is_connected = False

    async def resolve_peer(self, ref: Any, *, timeout: float = 20.0) -> Any:
        self._record("resolve_peer", (ref,), {"timeout": timeout})

        class _Peer:
            def __init__(self, *, peer_type: str, peer_id: int) -> None:
                self.peer_type = peer_type
                self.peer_id = peer_id

        if hasattr(ref, "peer_type") and hasattr(ref, "peer_id"):
            return ref

        if isinstance(ref, str):
            s = ref.strip()
            lower = s.lower()
            if lower.startswith(("user:", "@", "+")):
                tail = s.split(":", 1)[1] if ":" in s else ""
                peer_id = int(tail) if tail.isdigit() else 777
                return _Peer(peer_type="user", peer_id=peer_id)
            if lower.startswith(("channel:", "chat:", "group:")):
                tail = s.split(":", 1)[1] if ":" in s else ""
                peer_id = int(tail) if tail.isdigit() else 777
                return _Peer(peer_type="channel", peer_id=peer_id)

        return _Peer(peer_type="channel", peer_id=777)

    async def invoke_api(self, req: Any, *, timeout: float = 20.0) -> Any:
        self._record("invoke_api", (req,), {"timeout": timeout})
        return {"ok": True, "kind": "invoke_api", "request": type(req).__name__}

    async def prime_entities(
        self,
        *,
        limit: int = 100,
        folder_id: int | None = None,
        timeout: float = 20.0,
    ) -> None:
        self._record(
            "prime_entities",
            (),
            {"limit": limit, "folder_id": folder_id, "timeout": timeout},
        )

    async def iter_dialogs(
        self,
        *,
        limit: int = 100,
        folder_id: int | None = None,
        timeout: float = 20.0,
    ):
        self._record(
            "iter_dialogs",
            (),
            {"limit": limit, "folder_id": folder_id, "timeout": timeout},
        )
        yield {"dialog": 1}
        yield {"dialog": 2}

    async def iter_messages(self, peer: Any, *, limit: int = 100, timeout: float = 20.0):
        self._record("iter_messages", (peer,), {"limit": limit, "timeout": timeout})
        yield {"message": 1}
        yield {"message": 2}

    def __getattr__(self, name: str) -> Any:
        async def _call(*args: Any, **kwargs: Any) -> Any:
            self._record(name, args, kwargs)
            return {"ok": True, "raw_method": name, "args": args, "kwargs": kwargs}

        return _call


def _normalize_token(token: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", token.lower()).strip("_")


def _load_matrix() -> list[dict[str, Any]]:
    return json.loads(MATRIX_PATH.read_text(encoding="utf-8"))


def _resolve_method(client: Client, namespace: str, method: str) -> Any:
    obj: Any = client
    if namespace != "client":
        for part in namespace.split("."):
            obj = getattr(obj, part)
    return getattr(obj, method)


def _default_value(namespace: str, method: str, param_name: str) -> Any:
    key = (namespace, method, param_name)
    if key in METHOD_PARAM_OVERRIDES:
        return METHOD_PARAM_OVERRIDES[key]

    if param_name == "peer":
        return "user:1"
    if param_name in {"channel", "group", "from_group", "to_group"}:
        return "channel:1"
    if param_name in {"user", "from_peer"}:
        return "user:1"
    if param_name == "bot":
        return "user:1"
    if param_name == "to_peer":
        return "user:2"
    if param_name == "ref":
        return GiftRef.user_msg(1)
    if param_name == "refs":
        return [GiftRef.user_msg(1)]
    if param_name == "chatlist":
        return ChatlistRef.by_filter(1)
    if param_name == "target":
        return NotifyTarget.users()
    if param_name == "peer_target":
        return NotifyTarget.users()
    if param_name == "key":
        return object()
    if param_name in {
        "settings",
        "status",
        "emoji_status",
        "media",
        "reaction",
        "link_obj",
        "intro_obj_or_none",
        "work_hours_obj_or_none",
        "message_obj_or_none",
        "filter_obj_or_none",
    }:
        return object()
    if param_name in {"rules", "privacy_rules"}:
        return [object()]
    if param_name == "sticker_set":
        return StickerSetRef.short_name("telecraft_set")
    if param_name == "document":
        return DocumentRef.from_parts(1, 2, b"r")
    if param_name == "document_ids":
        return [1, 2]
    if param_name == "peers":
        return ["user:1", "channel:1"]
    if param_name == "topics":
        return [1, 2]
    if param_name == "ids":
        return [1, 2]
    if param_name == "order":
        return [1, 2]
    if param_name == "tx_ids":
        return ["tx-1"]
    if param_name == "invoice":
        return object()
    if param_name == "inline_message_id":
        return {"inline_message": "abc"}
    if param_name == "users":
        return ["user:2"]
    if param_name == "items":
        return ["item-a", "item-b"]
    if param_name == "item_ids":
        return [1, 2]
    if param_name == "usernames":
        return ["u1", "u2"]
    if param_name == "call_ref":
        return GroupCallRef.from_parts(1, 2)
    if param_name == "scopes":
        return TakeoutScopes()
    if param_name == "token_or_graph_obj":
        return "graph-token"
    if param_name == "paths":
        return ["/tmp/a.bin", "/tmp/b.bin"]
    if param_name == "captions":
        return ["a", "b"]
    if param_name == "assignments":
        return [FolderAssignment.of("user:1", 1), FolderAssignment.of("channel:1", 0)]
    if param_name == "form_id_msg_id_or_invoice":
        return InvoiceRef.by_message("user:1", 1)
    if param_name == "path":
        return "/tmp/sample.bin"
    if param_name == "dest":
        return "/tmp"
    if param_name in {"msg_ids", "folder_ids"}:
        return [1, 2]
    if param_name == "documents":
        return [1, 2]
    if param_name in {
        "chat_id",
        "user_id",
        "channel_id",
        "msg_id",
        "folder_id",
        "offset",
        "offset_id",
        "limit",
        "min_date",
        "max_date",
        "period",
        "heading",
        "accuracy_radius",
        "proximity_notification_radius",
        "close_period",
        "close_date",
        "until_date",
        "correct_option",
        "length",
        "fwd_limit",
        "sticker_id",
        "sticker_access_hash",
        "gift_id",
        "saved_id",
        "effect_id",
        "read_max_id",
        "count",
        "send_paid_messages_stars",
        "amount",
        "nanos",
        "score",
        "form_id",
        "sub_chain_id",
        "album_id",
        "random_id",
    }:
        return 1
    if param_name in {"latitude", "longitude"}:
        return 1.0
    if param_name in {
        "text",
        "title",
        "about",
        "query",
        "url",
        "username",
        "reason",
        "message",
        "question",
        "explanation",
        "first_name",
        "last_name",
        "vcard",
        "phone_number",
        "action",
        "rank",
        "method",
        "name",
        "slug",
        "shortcut",
        "emoticon",
        "charge_id",
        "result_id",
        "prepared_id",
        "passkey_id",
        "button_text",
        "params",
    }:
        return "x"
    if param_name == "data":
        return b"x"
    if param_name == "payload":
        return {"a": 1}
    if param_name == "theme":
        return "🔥"
    if param_name == "block":
        return b"block-data"
    if param_name == "credential":
        return object()
    if param_name == "available_reactions":
        return object()
    if param_name == "birthday":
        return object()
    if param_name == "tab":
        return object()
    if param_name == "stories":
        return [1, 2]
    if param_name == "invoice_media":
        return object()
    if param_name == "option":
        return b"option"
    if param_name == "options":
        return ["yes", "no"]
    if param_name == "photo_ids":
        return [(1, 2)]
    if param_name == "sticker_file_reference":
        return b"ref"
    if param_name == "network":
        return "prod"
    if param_name == "dc_id":
        return 2
    if param_name == "port":
        return 443
    if param_name == "framing":
        return "intermediate"
    return 1


FORWARDED_ARG_ALIASES: dict[str, tuple[str, ...]] = {
    "assignments": ("folder_peers",),
    "call_ref": ("call", "peer"),
    "ids": ("id",),
    "effect_id": ("effect",),
    "form_id_msg_id_or_invoice": ("invoice",),
    "invoice_media": ("invoice_media",),
    "inline_message_id": ("id",),
    "item_ids": ("completed", "incompleted"),
    "msg_ids": ("id", "msg_id"),
    "msg_id": ("id",),
    "reply_to_msg_id": ("reply_to",),
    "result_id": ("id",),
    "method": ("custom_method",),
    "query_obj": ("query",),
    "reason": ("option",),
    "params": ("data",),
    "payload": ("data",),
    "text": ("message",),
    "theme": ("emoticon", "slug", "theme"),
    "tx_ids": ("id",),
    "ref": ("stargift",),
    "refs": ("stargift",),
    "users": ("id", "users"),
    "privacy": ("private",),
    "peers": ("id", "folder_peers"),
    "document": ("id",),
    "document_ids": ("document_id",),
    "filter_id": ("id",),
    "filter_obj_or_none": ("filter",),
    "intro_obj_or_none": ("intro",),
    "link_obj": ("link",),
    "message_obj_or_none": ("message",),
    "sticker_set": ("stickerset",),
    "query": ("q",),
    "story_id": ("id",),
    "target": ("peer",),
    "peer_target": ("peer",),
    "token_or_graph_obj": ("token",),
    "passkey_id": ("id",),
    "prepared_id": ("id",),
    "usernames": ("order",),
    "work_hours_obj_or_none": ("business_work_hours",),
}


def _is_sequence_value(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _matches_forwarded_value(expected: Any, actual: Any) -> bool:
    if actual == expected:
        return True
    if isinstance(expected, dict):
        if isinstance(actual, str):
            try:
                return json.loads(actual) == expected
            except Exception:  # noqa: BLE001
                return False
        if isinstance(actual, (bytes, bytearray)):
            try:
                return json.loads(bytes(actual).decode("utf-8")) == expected
            except Exception:  # noqa: BLE001
                return False
    if _is_sequence_value(expected) and _is_sequence_value(actual):
        return len(expected) == len(actual)
    if isinstance(
        expected,
        (
            GiftRef,
            GroupCallRef,
            InvoiceRef,
            StickerSetRef,
            DocumentRef,
            NotifyTarget,
            ChatlistRef,
            TakeoutScopes,
        ),
    ):
        # Ref/helper values are intentionally converted to TL input objects.
        return actual is not None
    return False


def _iter_nested_values(root: Any, *, max_depth: int = 4) -> list[Any]:
    values: list[Any] = []
    stack: list[tuple[Any, int]] = [(root, 0)]
    seen: set[int] = set()

    while stack:
        value, depth = stack.pop()
        value_id = id(value)
        if value_id in seen:
            continue
        seen.add(value_id)
        values.append(value)

        if depth >= max_depth:
            continue
        if isinstance(value, (str, bytes, bytearray, int, float, bool, type(None))):
            continue

        if _is_sequence_value(value):
            for item in value:
                stack.append((item, depth + 1))
            continue

        if isinstance(value, dict):
            for item in value.values():
                stack.append((item, depth + 1))
            continue

        maybe_dict = getattr(value, "__dict__", None)
        if isinstance(maybe_dict, dict):
            for item in maybe_dict.values():
                stack.append((item, depth + 1))

        slots = getattr(type(value), "__slots__", ())
        if isinstance(slots, str):
            slots = (slots,)
        for slot in slots:
            if slot.startswith("_"):
                continue
            if hasattr(value, slot):
                stack.append((getattr(value, slot), depth + 1))

    return values


def _arg_forwarded(raw: SpyRaw, name: str, value: Any) -> bool:
    candidate_names = (name,) + FORWARDED_ARG_ALIASES.get(name, ())

    for call in raw.calls:
        containers = [*call.args, *call.kwargs.values()]
        for candidate in candidate_names:
            if candidate in call.kwargs and _matches_forwarded_value(value, call.kwargs[candidate]):
                return True
            for container in containers:
                for nested in _iter_nested_values(container):
                    if isinstance(nested, dict):
                        if candidate in nested and _matches_forwarded_value(
                            value, nested[candidate]
                        ):
                            return True
                    if hasattr(nested, candidate) and _matches_forwarded_value(
                        value, getattr(nested, candidate)
                    ):
                        return True
        if any(_matches_forwarded_value(value, arg) for arg in call.args):
            return True
        if any(_matches_forwarded_value(value, kw) for kw in call.kwargs.values()):
            return True
        for arg in call.args:
            for candidate in candidate_names:
                if hasattr(arg, candidate) and _matches_forwarded_value(
                    value, getattr(arg, candidate)
                ):
                    return True
    return False


def _build_inputs(
    *,
    namespace: str,
    method: str,
    bound_method: Any,
    include_timeout: bool,
) -> tuple[list[Any], dict[str, Any], dict[str, Any]]:
    sig = inspect.signature(bound_method)
    args: list[Any] = []
    kwargs: dict[str, Any] = {}
    expected_required: dict[str, Any] = {}
    always_include = OPTIONAL_REQUIRED_PARAMS.get((namespace, method), set())

    for param in sig.parameters.values():
        if param.name == "self":
            continue

        if param.name == "timeout":
            if include_timeout:
                kwargs["timeout"] = DEFAULT_TIMEOUT
            continue

        value = _default_value(namespace, method, param.name)
        required = param.default is inspect._empty

        if required or param.name in always_include:
            expected_required[param.name] = value
            if param.kind in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            ):
                args.append(value)
            else:
                kwargs[param.name] = value

    return args, kwargs, expected_required


async def _invoke(bound_method: Any, args: list[Any], kwargs: dict[str, Any]) -> Any:
    out = bound_method(*args, **kwargs)
    if inspect.isasyncgen(out):
        values = []
        async for item in out:
            values.append(item)
        return values
    return await out


async def _run_scenario(namespace: str, method: str, scenario: str) -> None:
    raw = SpyRaw()
    client = Client(raw=raw)
    bound = _resolve_method(client, namespace, method)

    if scenario == "handles_rpc_error":
        first_args, first_kwargs, _ = _build_inputs(
            namespace=namespace,
            method=method,
            bound_method=bound,
            include_timeout=False,
        )
        await _invoke(bound, first_args, first_kwargs)
        assert raw.calls, f"{namespace}.{method} did not call raw before rpc error check"
        first_name = raw.calls[0].name

        raw = SpyRaw()
        raw.raise_on.add(first_name)
        client = Client(raw=raw)
        bound = _resolve_method(client, namespace, method)
        args, kwargs, _ = _build_inputs(
            namespace=namespace,
            method=method,
            bound_method=bound,
            include_timeout=False,
        )
        try:
            await _invoke(bound, args, kwargs)
        except DummyRpcError:
            return
        raise AssertionError(f"{namespace}.{method} did not bubble DummyRpcError from {first_name}")

    include_timeout = scenario == "passes_timeout"
    args, kwargs, expected_required = _build_inputs(
        namespace=namespace,
        method=method,
        bound_method=bound,
        include_timeout=include_timeout,
    )
    result = await _invoke(bound, args, kwargs)

    if scenario == "delegates_to_raw":
        assert raw.calls, f"{namespace}.{method} did not delegate to raw"
        return

    if scenario == "passes_timeout":
        assert raw.calls, f"{namespace}.{method} did not call raw for timeout check"
        assert any(call.kwargs.get("timeout") == DEFAULT_TIMEOUT for call in raw.calls), (
            f"{namespace}.{method} did not pass timeout={DEFAULT_TIMEOUT}"
        )
        return

    if scenario == "forwards_args":
        assert raw.calls, f"{namespace}.{method} did not call raw for arg forwarding"
        for name, value in expected_required.items():
            if _arg_forwarded(raw, name, value):
                continue
            raise AssertionError(
                f"{namespace}.{method} did not forward required arg {name!r} with value {value!r}"
            )
        return

    if scenario == "returns_expected_shape":
        key = (namespace, method)
        if key in VOID_METHODS:
            assert result is None
            return
        if key in ASYNC_ITER_METHODS:
            assert result == [{"dialog": 1}, {"dialog": 2}] or result == [
                {"message": 1},
                {"message": 2},
            ]
            return
        if isinstance(result, dict):
            assert result.get("ok") is True
            return
        assert result is not None
        return

    raise AssertionError(f"Unsupported scenario {scenario!r} for {namespace}.{method}")


def _make_test(namespace: str, method: str, scenario: str):
    def _test() -> None:
        asyncio.run(_run_scenario(namespace, method, scenario))

    ns = _normalize_token(namespace)
    meth = _normalize_token(method)
    scen = _normalize_token(scenario)
    _test.__name__ = f"test_{ns}__{meth}__{scen}"
    return _test


for _row in _load_matrix():
    _namespace = str(_row["namespace"])
    _method = str(_row["method"])
    for _scenario in _row["required_scenarios"]:
        if _scenario not in UNIT_SCENARIOS:
            continue
        _fn = _make_test(_namespace, _method, str(_scenario))
        globals()[_fn.__name__] = _fn


def test_messages__react__rejects_dual_aliases() -> None:
    async def _case() -> None:
        c = Client(raw=SpyRaw())
        try:
            await c.messages.react("user:1", 1, reaction="👍", emoji="🔥")
        except ValueError:
            return
        raise AssertionError("messages.react should reject reaction+emoji together")

    asyncio.run(_case())
