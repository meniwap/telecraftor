from __future__ import annotations

import struct

import pytest

from telecraft.mtproto.core.msg_id import MsgIdGenerator
from telecraft.mtproto.core.state import (
    MtprotoState,
    MtprotoStateError,
    _calc_key_iv_mtproto2,
)
from telecraft.mtproto.crypto.aes_ige import AesIge
from telecraft.mtproto.crypto.hashes import sha256

_SERVER_MSG_ID = (1_700_000_000 << 32) | 1


def _state() -> MtprotoState:
    return MtprotoState(
        auth_key=bytes(range(256)),
        server_salt=b"\x11" * 8,
        session_id=b"\x22" * 8,
        msg_id_gen=MsgIdGenerator(),
    )


def _server_packet(
    state: MtprotoState,
    *,
    declared_length: int,
    body: bytes,
    padding: bytes,
) -> bytes:
    inner = struct.pack("<qii", _SERVER_MSG_ID, 1, declared_length) + body
    plain = state.server_salt + state.session_id + inner + padding
    assert len(plain) % 16 == 0

    msg_key = sha256(state.auth_key[96:128] + plain)[8:24]
    aes_key, aes_iv = _calc_key_iv_mtproto2(
        auth_key=state.auth_key,
        msg_key=msg_key,
        client=False,
    )
    encrypted = AesIge(key=aes_key, iv=aes_iv).encrypt(plain)
    return struct.pack("<Q", state.auth_key_id) + msg_key + encrypted


@pytest.mark.parametrize(
    ("body", "padding"),
    [
        (b"body", b"\xaa" * 12),
        (b"", b"\xaa" * 1024),
    ],
)
def test_decrypt_packet_accepts_padding_boundaries(body: bytes, padding: bytes) -> None:
    state = _state()
    packet = _server_packet(
        state,
        declared_length=len(body),
        body=body,
        padding=padding,
    )

    assert state.decrypt_packet(packet, from_server=True) == (
        struct.pack("<qii", _SERVER_MSG_ID, 1, len(body)) + body
    )


@pytest.mark.parametrize(
    ("body", "padding"),
    [
        (b"12345678", b"\xaa" * 8),
        (b"body", b"\xaa" * 1036),
    ],
)
def test_decrypt_packet_rejects_padding_outside_mtproto2_bounds(
    body: bytes,
    padding: bytes,
) -> None:
    state = _state()
    packet = _server_packet(
        state,
        declared_length=len(body),
        body=body,
        padding=padding,
    )

    with pytest.raises(MtprotoStateError, match="padding length"):
        state.decrypt_packet(packet, from_server=True)


def test_decrypt_packet_rejects_unaligned_body_length() -> None:
    state = _state()
    packet = _server_packet(
        state,
        declared_length=1,
        body=b"x",
        padding=b"\xaa" * 15,
    )

    with pytest.raises(MtprotoStateError, match="divisible by 4"):
        state.decrypt_packet(packet, from_server=True)


def test_decrypt_packet_rejects_body_length_beyond_payload() -> None:
    state = _state()
    packet = _server_packet(
        state,
        declared_length=32,
        body=b"",
        padding=b"\xaa" * 16,
    )

    with pytest.raises(MtprotoStateError, match="body exceeds"):
        state.decrypt_packet(packet, from_server=True)


def test_decrypt_packet_rejects_non_block_aligned_ciphertext() -> None:
    state = _state()
    inner = struct.pack("<qii", _SERVER_MSG_ID, 1, 4) + b"body"
    packet = state.encrypt_inner_message(inner, to_server=False)

    with pytest.raises(MtprotoStateError, match="multiple of 16"):
        state.decrypt_packet(packet[:-1], from_server=True)


def test_decrypt_packet_rejects_msg_key_mismatch() -> None:
    state = _state()
    inner = struct.pack("<qii", _SERVER_MSG_ID, 1, 4) + b"body"
    packet = state.encrypt_inner_message(inner, to_server=False)
    tampered_msg_key = bytes([packet[8] ^ 1]) + packet[9:24]
    tampered_packet = packet[:8] + tampered_msg_key + packet[24:]

    with pytest.raises(MtprotoStateError, match="msg_key mismatch"):
        state.decrypt_packet(tampered_packet, from_server=True)


def test_decrypt_packet_rejects_session_id_mismatch() -> None:
    state = _state()
    inner = struct.pack("<qii", _SERVER_MSG_ID, 1, 4) + b"body"
    packet = state.encrypt_inner_message(inner, to_server=False)
    state.session_id = b"\x33" * 8

    with pytest.raises(MtprotoStateError, match="session_id mismatch"):
        state.decrypt_packet(packet, from_server=True)


def test_decrypt_packet_strips_valid_random_padding() -> None:
    state = _state()
    inner = struct.pack("<qii", _SERVER_MSG_ID, 1, 4) + b"body"

    packet = state.encrypt_inner_message(inner, to_server=False)

    assert state.decrypt_packet(packet, from_server=True) == inner
