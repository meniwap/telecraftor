from __future__ import annotations

import gzip
import struct

import pytest

from telecraft.mtproto.gzip_utils import MAX_GZIP_UNPACKED_SIZE
from telecraft.tl.codec import (
    MsgContainer,
    RpcResult,
    TLCodecError,
    TrailingTLDataError,
    dumps,
    loads,
)
from telecraft.tl.generated.types import Pong, RpcError, UserEmpty

_RPC_RESULT_CONSTRUCTOR_ID = -212046591
_MSG_CONTAINER_CONSTRUCTOR_ID = 1945237724
_GZIP_PACKED_CONSTRUCTOR_ID = 812830625
_VECTOR_CONSTRUCTOR_ID = 481674261


def _tl_bytes(data: bytes) -> bytes:
    ln = len(data)
    if ln < 254:
        out = bytes([ln]) + data
        out += b"\x00" * ((4 - ((1 + ln) % 4)) % 4)
        return out
    out = bytes([254]) + struct.pack("<I", ln)[:3] + data
    out += b"\x00" * ((4 - ((4 + ln) % 4)) % 4)
    return out


def _rpc_result(req_msg_id: int, result: bytes) -> bytes:
    return struct.pack("<iq", _RPC_RESULT_CONSTRUCTOR_ID, req_msg_id) + result


def _vector(*items: bytes) -> bytes:
    return struct.pack("<ii", _VECTOR_CONSTRUCTOR_ID, len(items)) + b"".join(items)


def _gzip_packed(payload: bytes) -> bytes:
    return struct.pack("<i", _GZIP_PACKED_CONSTRUCTOR_ID) + _tl_bytes(gzip.compress(payload))


def _at_boundary(payload: bytes, boundary: str) -> bytes:
    if boundary == "direct":
        return payload
    if boundary == "container":
        return (
            struct.pack("<ii", _MSG_CONTAINER_CONSTRUCTOR_ID, 1)
            + struct.pack("<qii", 1111, 1, len(payload))
            + payload
        )
    if boundary == "gzip":
        return _gzip_packed(payload)
    raise AssertionError(f"unexpected test boundary: {boundary}")


def _rpc_result_at_boundary(obj: object, boundary: str) -> RpcResult:
    if boundary == "container":
        assert isinstance(obj, MsgContainer)
        assert len(obj.messages) == 1
        result = obj.messages[0].obj
    else:
        result = obj
    assert isinstance(result, RpcResult)
    return result


def test_parse_rpc_result() -> None:
    pong = Pong(msg_id=123, ping_id=456)
    payload = dumps(pong)
    rpc_result_cid = -212046591  # 0xF35C6D01
    data = struct.pack("<i", rpc_result_cid) + struct.pack("<q", 777) + payload
    obj = loads(data)
    assert isinstance(obj, RpcResult)
    assert obj.req_msg_id == 777
    assert isinstance(obj.result, Pong)


@pytest.mark.parametrize("boundary", ["direct", "container", "gzip"])
@pytest.mark.parametrize(
    ("result_type", "wire_items", "expected"),
    [
        pytest.param(
            "Vector<User>",
            [dumps(UserEmpty(id=123)), dumps(UserEmpty(id=456))],
            [UserEmpty(id=123), UserEmpty(id=456)],
            id="users",
        ),
        pytest.param(
            "Vector<int>",
            [struct.pack("<i", 123), struct.pack("<i", -456)],
            [123, -456],
            id="ints",
        ),
        pytest.param(
            "Vector<long>",
            [struct.pack("<q", 2**40), struct.pack("<q", -(2**41))],
            [2**40, -(2**41)],
            id="longs",
        ),
    ],
)
def test_rpc_result_uses_pending_result_type_at_every_bounded_envelope(
    boundary: str,
    result_type: str,
    wire_items: list[bytes],
    expected: list[object],
) -> None:
    req_msg_id = 777
    payload = _at_boundary(
        _rpc_result(req_msg_id, _vector(*wire_items)),
        boundary,
    )

    decoded = loads(payload, rpc_result_types={req_msg_id: result_type})
    rpc_result = _rpc_result_at_boundary(decoded, boundary)

    assert rpc_result.req_msg_id == req_msg_id
    assert rpc_result.result == expected


def test_rpc_result_typed_vector_may_be_gzip_packed_without_weakening_its_boundary() -> None:
    req_msg_id = 778
    data = _rpc_result(
        req_msg_id,
        _gzip_packed(_vector(dumps(UserEmpty(id=789)))),
    )

    decoded = loads(data, rpc_result_types={req_msg_id: "Vector<User>"})

    assert isinstance(decoded, RpcResult)
    assert decoded.result == [UserEmpty(id=789)]


def test_rpc_result_expected_vector_decodes_gzip_packed_rpc_error() -> None:
    req_msg_id = 781
    error = RpcError(error_code=400, error_message=b"BAD_REQUEST")
    data = _rpc_result(req_msg_id, _gzip_packed(dumps(error)))

    decoded = loads(data, rpc_result_types={req_msg_id: "Vector<User>"})

    assert isinstance(decoded, RpcResult)
    assert isinstance(decoded.result, RpcError)
    assert decoded.result.error_code == 400
    assert decoded.result.error_message == b"BAD_REQUEST"


def test_rpc_result_typed_vector_rejects_trailing_bytes() -> None:
    req_msg_id = 779
    data = _rpc_result(
        req_msg_id,
        _vector(struct.pack("<i", 123)) + b"\x00\x00\x00\x00",
    )

    with pytest.raises(TrailingTLDataError):
        loads(data, rpc_result_types={req_msg_id: "Vector<int>"})


def test_rpc_result_vector_without_a_result_type_remains_fail_closed() -> None:
    req_msg_id = 780
    data = _rpc_result(req_msg_id, _vector(struct.pack("<i", 123)))

    with pytest.raises(TLCodecError):
        loads(data, rpc_result_types={})


def test_bare_vector_constructor_without_result_context_remains_fail_closed() -> None:
    data = struct.pack("<i", _VECTOR_CONSTRUCTOR_ID)

    with pytest.raises(TLCodecError, match="[Vv]ector"):
        loads(data)


def test_parse_gzip_packed_unwraps() -> None:
    pong = Pong(msg_id=1, ping_id=2)
    inner = dumps(pong)
    packed = gzip.compress(inner)
    gzip_packed_cid = 812830625  # 0x3072CFA1
    data = struct.pack("<i", gzip_packed_cid) + _tl_bytes(packed)
    obj = loads(data)
    assert isinstance(obj, Pong)
    assert obj.ping_id == 2


def test_parse_gzip_packed_rejects_oversized_payload() -> None:
    packed = gzip.compress(b"\x00" * (MAX_GZIP_UNPACKED_SIZE + 1))
    gzip_packed_cid = 812830625  # 0x3072CFA1
    data = struct.pack("<i", gzip_packed_cid) + _tl_bytes(packed)

    with pytest.raises(TLCodecError, match="gzip_packed"):
        loads(data)


def test_parse_gzip_packed_rejects_malformed_payload() -> None:
    gzip_packed_cid = 812830625  # 0x3072CFA1
    data = struct.pack("<i", gzip_packed_cid) + _tl_bytes(b"not gzip")

    with pytest.raises(TLCodecError, match="gzip_packed"):
        loads(data)


def test_parse_msg_container() -> None:
    pong = Pong(msg_id=10, ping_id=20)
    rpc_result_cid = -212046591  # 0xF35C6D01
    inner_obj = struct.pack("<i", rpc_result_cid) + struct.pack("<q", 999) + dumps(pong)

    msg_container_cid = 1945237724  # 0x73F1F8DC
    msg_id = 1111
    seqno = 1
    data = (
        struct.pack("<i", msg_container_cid)
        + struct.pack("<i", 1)  # count
        + struct.pack("<q", msg_id)
        + struct.pack("<i", seqno)
        + struct.pack("<i", len(inner_obj))
        + inner_obj
    )

    obj = loads(data)
    assert isinstance(obj, MsgContainer)
    assert len(obj.messages) == 1
    assert obj.messages[0].msg_id == msg_id
    assert obj.messages[0].seqno == seqno
    assert isinstance(obj.messages[0].obj, RpcResult)
    assert isinstance(obj.messages[0].obj.result, Pong)


def test_root_bounded_payload_rejects_trailing_bytes() -> None:
    with pytest.raises(TrailingTLDataError) as raised:
        loads(dumps(Pong(msg_id=1, ping_id=2)) + b"\x00\x00\x00\x00")

    assert raised.value.path == "root"
    assert raised.value.trailing_bytes == 4


def test_gzip_bounded_payload_rejects_trailing_bytes() -> None:
    inner = dumps(Pong(msg_id=1, ping_id=2)) + b"\x00\x00\x00\x00"
    data = struct.pack("<i", 812830625) + _tl_bytes(gzip.compress(inner))

    with pytest.raises(TrailingTLDataError) as raised:
        loads(data)

    assert raised.value.path == "root.gzip_packed"
    assert raised.value.trailing_bytes == 4


def test_msg_container_bounded_inner_payload_rejects_trailing_bytes() -> None:
    inner = dumps(Pong(msg_id=1, ping_id=2)) + b"\x00\x00\x00\x00"
    data = struct.pack("<ii", 1945237724, 1) + struct.pack("<qii", 1111, 1, len(inner)) + inner

    with pytest.raises(TrailingTLDataError) as raised:
        loads(data)

    assert raised.value.path == "root.msg_container[0]"
    assert raised.value.trailing_bytes == 4
