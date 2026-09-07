from __future__ import annotations

import gzip
import struct

import pytest

from telecraft.tl.codec import (
    VECTOR_CONSTRUCTOR_ID,
    TLCodecError,
    TLReader,
    TLWriter,
    dumps,
    loads,
)
from telecraft.tl.generated import types as public_types
from telecraft.tl.generated._legacy_types import (
    _LegacyMessage9815CEC8,
    _LegacyMessageB92F76CF,
)
from telecraft.tl.generated.types import (
    Message,
    MessageEmpty,
    MessageMediaDice,
    MessageMediaPoll,
    MessagesChannelMessages,
    PeerChannel,
    Poll,
    PollAnswer,
    PollAnswerVoters,
    PollResults,
    TextWithEntities,
    UpdateNewChannelMessage,
)

_LAYER_216_MESSAGE = -1743401272  # 0x9815cec8
_LAYER_220_MESSAGE = -1188071729  # 0xb92f76cf
_GZIP_PACKED = 812830625
_LEGACY_MESSAGE_MEDIA_POLL = 1272375192  # 0x4bd6e798
_LEGACY_POLL = 1484026161  # 0x58747131
_LEGACY_POLL_RESULTS = 2061444128  # 0x7adf2420
_LEGACY_POLL_ANSWER = -15277366  # 0xff16e2ca
_LEGACY_POLL_ANSWER_VOTERS = 997055186  # 0x3b6ddad2


def _legacy_message(
    constructor_id: int,
    *,
    flags: int = 0,
    flags2: int = 0,
    message_id: int = 42,
    text: bytes = b"legacy wire, current post",
    schedule_repeat_period: int | None = None,
    media_dice: tuple[int, bytes] | None = None,
) -> bytes:
    writer = TLWriter()
    writer.write_int(constructor_id)
    writer.write_int(flags)
    writer.write_int(flags2)
    writer.write_int(message_id)
    writer.write_object(PeerChannel(channel_id=777))
    writer.write_int(1_788_000_000)
    writer.write_string(text)
    if flags & (1 << 9):
        assert media_dice is not None
        writer.write_int(0x3F7EE58B)
        writer.write_int(media_dice[0])
        writer.write_string(media_dice[1])
    if flags2 & (1 << 10):
        assert constructor_id == _LAYER_220_MESSAGE
        assert schedule_repeat_period is not None
        writer.write_int(schedule_repeat_period)
    return writer.to_bytes()


def _legacy_message_with_scalar_optionals(constructor_id: int) -> bytes:
    flags = sum(
        1 << bit
        for bit in (
            1,  # out
            4,  # mentioned
            5,  # media_unread
            8,  # from_id
            10,  # views + forwards
            11,  # via_bot_id
            13,  # silent
            14,  # post
            15,  # edit_date
            16,  # post_author
            17,  # grouped_id
            18,  # from_scheduled
            19,  # legacy
            21,  # edit_hide
            24,  # pinned
            25,  # ttl_period
            26,  # noforwards
            27,  # invert_media
            28,  # saved_peer_id
            29,  # from_boosts_applied
            30,  # quick_reply_shortcut_id
        )
    )
    flags2 = sum(
        1 << bit
        for bit in (
            0,  # via_business_bot_id
            1,  # offline
            2,  # effect
            4,  # video_processing_pending
            5,  # report_delivery_until_date
            6,  # paid_message_stars
            8,  # paid_suggested_post_stars
            9,  # paid_suggested_post_ton
        )
    )
    if constructor_id == _LAYER_220_MESSAGE:
        flags2 |= 1 << 10

    writer = TLWriter()
    writer.write_int(constructor_id)
    writer.write_int(flags)
    writer.write_int(flags2)
    writer.write_int(9001)
    writer.write_object(PeerChannel(channel_id=101))
    writer.write_int(7)
    writer.write_object(PeerChannel(channel_id=202))
    writer.write_object(PeerChannel(channel_id=303))
    writer.write_long(4_004)
    writer.write_long(5_005)
    writer.write_int(1_788_000_001)
    writer.write_string(b"all scalar branches")
    writer.write_int(6_006)
    writer.write_int(7_007)
    writer.write_int(1_788_000_002)
    writer.write_string(b"legacy author")
    writer.write_long(8_008)
    writer.write_int(9_009)
    writer.write_int(10_010)
    writer.write_long(11_011)
    writer.write_int(1_788_000_003)
    writer.write_long(12_012)
    if constructor_id == _LAYER_220_MESSAGE:
        writer.write_int(86_400)
    return writer.to_bytes()


def _legacy_message_with_legacy_poll() -> bytes:
    writer = TLWriter()
    writer.write_int(_LAYER_216_MESSAGE)
    writer.write_int(1 << 9)  # media
    writer.write_int(0)
    writer.write_int(123)
    writer.write_object(PeerChannel(channel_id=777))
    writer.write_int(1_788_000_000)
    writer.write_string(b"poll")

    writer.write_int(_LEGACY_MESSAGE_MEDIA_POLL)
    writer.write_int(_LEGACY_POLL)
    writer.write_long(4_242)
    poll_flags = sum(1 << bit for bit in range(10))
    writer.write_int(poll_flags)
    writer.write_object(TextWithEntities(text=b"Old question", entities=[]))
    writer.write_int(VECTOR_CONSTRUCTOR_ID)
    writer.write_int(1)
    writer.write_int(_LEGACY_POLL_ANSWER)
    writer.write_object(TextWithEntities(text=b"Old answer", entities=[]))
    writer.write_bytes(b"A")
    writer.write_int(60)
    writer.write_int(1_788_000_060)

    writer.write_int(_LEGACY_POLL_RESULTS)
    poll_results_flags = sum(1 << bit for bit in range(5))
    writer.write_int(poll_results_flags)
    writer.write_int(VECTOR_CONSTRUCTOR_ID)
    writer.write_int(1)
    writer.write_int(_LEGACY_POLL_ANSWER_VOTERS)
    writer.write_int((1 << 0) | (1 << 1))
    writer.write_bytes(b"A")
    writer.write_int(23)
    writer.write_int(23)
    writer.write_int(VECTOR_CONSTRUCTOR_ID)
    writer.write_int(1)
    writer.write_object(PeerChannel(channel_id=888))
    writer.write_string(b"Because it is correct")
    writer.write_int(VECTOR_CONSTRUCTOR_ID)
    writer.write_int(0)
    return writer.to_bytes()


@pytest.mark.parametrize("constructor_id", [_LAYER_216_MESSAGE, _LAYER_220_MESSAGE])
def test_legacy_messages_decode_to_current_public_message(constructor_id: int) -> None:
    decoded = loads(_legacy_message(constructor_id, flags=1 << 1))

    assert type(decoded) is Message
    assert decoded.TL_ID == 0x7600B9D3
    assert decoded.id == 42
    assert decoded.out is True
    assert decoded.message == b"legacy wire, current post"
    assert isinstance(decoded.peer_id, PeerChannel)
    assert decoded.from_rank is None
    assert decoded.guestchat_via_from is None
    assert decoded.summary_from_language is None
    assert decoded.rich_message is None
    assert decoded.schedule_repeat_period is None

    encoded = dumps(decoded)
    assert struct.unpack_from("<I", encoded)[0] == 0x7600B9D3


@pytest.mark.parametrize(
    ("constructor_id", "schedule_repeat_period"),
    [
        (_LAYER_216_MESSAGE, None),
        (_LAYER_220_MESSAGE, 86_400),
    ],
)
def test_legacy_message_decodes_inside_channel_messages_at_the_exact_boundary(
    constructor_id: int,
    schedule_repeat_period: int | None,
) -> None:
    first = _legacy_message(
        constructor_id,
        flags2=(1 << 10) if schedule_repeat_period is not None else 0,
        schedule_repeat_period=schedule_repeat_period,
    )
    second = dumps(MessageEmpty(flags=0, id=99, peer_id=None))
    payload = (
        struct.pack("<iiiiii", MessagesChannelMessages.TL_ID, 0, 51, 2, 0x1CB5C415, 2)
        + first
        + second
        + struct.pack("<ii", 0x1CB5C415, 0) * 3
    )

    decoded = loads(payload)

    assert isinstance(decoded, MessagesChannelMessages)
    assert len(decoded.messages) == 2
    assert type(decoded.messages[0]) is Message
    assert decoded.messages[0].schedule_repeat_period == schedule_repeat_period
    assert isinstance(decoded.messages[1], MessageEmpty)
    assert decoded.messages[1].id == 99


@pytest.mark.parametrize("constructor_id", [_LAYER_216_MESSAGE, _LAYER_220_MESSAGE])
def test_legacy_message_scalar_fields_follow_the_exact_historical_order(
    constructor_id: int,
) -> None:
    sentinel = dumps(MessageEmpty(flags=0, id=99, peer_id=None))
    reader = TLReader(_legacy_message_with_scalar_optionals(constructor_id) + sentinel)

    decoded = reader.read_object(path="messages[0]", expected_type="Message")
    trailing = reader.read_object(path="messages[1]", expected_type="Message")

    assert type(decoded) is Message
    assert decoded.id == 9001
    assert decoded.out is True
    assert decoded.mentioned is True
    assert decoded.media_unread is True
    assert decoded.offline is True
    assert decoded.video_processing_pending is True
    assert decoded.from_id.channel_id == 101
    assert decoded.from_boosts_applied == 7
    assert decoded.peer_id.channel_id == 202
    assert decoded.saved_peer_id.channel_id == 303
    assert decoded.via_bot_id == 4_004
    assert decoded.via_business_bot_id == 5_005
    assert decoded.views == 6_006
    assert decoded.forwards == 7_007
    assert decoded.edit_date == 1_788_000_002
    assert decoded.post_author == b"legacy author"
    assert decoded.grouped_id == 8_008
    assert decoded.ttl_period == 9_009
    assert decoded.quick_reply_shortcut_id == 10_010
    assert decoded.effect == 11_011
    assert decoded.report_delivery_until_date == 1_788_000_003
    assert decoded.paid_message_stars == 12_012
    assert decoded.schedule_repeat_period == (
        86_400 if constructor_id == _LAYER_220_MESSAGE else None
    )
    assert isinstance(trailing, MessageEmpty)
    assert reader._remaining() == 0


def test_legacy_message_normalizes_nested_legacy_media() -> None:
    decoded = loads(
        _legacy_message(
            _LAYER_216_MESSAGE,
            flags=1 << 9,
            media_dice=(6, b"\xf0\x9f\x8e\xb2"),
        )
    )

    assert type(decoded) is Message
    assert isinstance(decoded.media, MessageMediaDice)
    assert decoded.media.value == 6
    assert decoded.media.emoticon == b"\xf0\x9f\x8e\xb2"
    assert decoded.media.flags == 0
    assert decoded.media.game_outcome is None


def test_legacy_message_normalizes_complete_legacy_poll_graph_without_drift() -> None:
    sentinel = dumps(MessageEmpty(flags=0, id=999, peer_id=None))
    reader = TLReader(_legacy_message_with_legacy_poll() + sentinel)

    decoded = reader.read_object(path="messages[0]", expected_type="Message")
    trailing = reader.read_object(path="messages[1]", expected_type="Message")

    assert type(decoded) is Message
    assert isinstance(decoded.media, MessageMediaPoll)
    assert isinstance(decoded.media.poll, Poll)
    assert decoded.media.poll.id == 4_242
    assert decoded.media.poll.open_answers is True
    assert decoded.media.poll.revoting_disabled is True
    assert decoded.media.poll.shuffle_answers is True
    assert decoded.media.poll.hide_results_until_close is True
    assert decoded.media.poll.creator is False
    assert decoded.media.poll.subscribers_only is False
    assert decoded.media.poll.countries_iso2 is None
    assert decoded.media.poll.hash == 0
    assert len(decoded.media.poll.answers) == 1
    assert isinstance(decoded.media.poll.answers[0], PollAnswer)
    assert decoded.media.poll.answers[0].option == b"A"
    assert decoded.media.poll.answers[0].media is None

    assert isinstance(decoded.media.results, PollResults)
    assert decoded.media.results.min is True
    assert decoded.media.results.total_voters == 23
    assert decoded.media.results.solution == b"Because it is correct"
    assert decoded.media.results.solution_media is None
    assert len(decoded.media.results.results) == 1
    voters = decoded.media.results.results[0]
    assert isinstance(voters, PollAnswerVoters)
    assert voters.chosen is True
    assert voters.correct is True
    assert voters.voters == 23
    assert voters.recent_voters == []
    assert isinstance(decoded.media.results.recent_voters[0], PeerChannel)
    assert decoded.media.results.recent_voters[0].channel_id == 888
    assert isinstance(trailing, MessageEmpty)
    assert reader._remaining() == 0


@pytest.mark.parametrize("constructor_id", [_LAYER_216_MESSAGE, _LAYER_220_MESSAGE])
def test_legacy_message_decodes_inside_update_and_gzip(constructor_id: int) -> None:
    update = (
        struct.pack("<i", UpdateNewChannelMessage.TL_ID)
        + _legacy_message(constructor_id)
        + struct.pack("<ii", 12, 1)
    )
    writer = TLWriter()
    writer.write_int(_GZIP_PACKED)
    writer.write_bytes(gzip.compress(update))

    decoded = loads(writer.to_bytes())

    assert isinstance(decoded, UpdateNewChannelMessage)
    assert type(decoded.message) is Message
    assert decoded.pts == 12


@pytest.mark.parametrize(
    "legacy_class",
    [_LegacyMessage9815CEC8, _LegacyMessageB92F76CF],
)
def test_legacy_wire_classes_are_private_and_cannot_be_sent(legacy_class: type) -> None:
    assert legacy_class.__name__ not in public_types.__all__
    assert not hasattr(public_types, legacy_class.__name__)

    values = {name: None for name, _type_expr in legacy_class.TL_PARAMS}
    values.update(
        flags=0,
        flags2=0,
        id=1,
        peer_id=PeerChannel(channel_id=1),
        date=1,
        message=b"x",
    )
    legacy = legacy_class(**values)

    with pytest.raises(TLCodecError, match="Inbound-only"):
        dumps(legacy)


def test_reader_consumes_two_bare_legacy_messages_without_cursor_drift() -> None:
    payload = _legacy_message(_LAYER_216_MESSAGE) + _legacy_message(
        _LAYER_220_MESSAGE,
        message_id=43,
    )
    reader = TLReader(payload)

    first = reader.read_object(path="messages[0]", expected_type="Message")
    second = reader.read_object(path="messages[1]", expected_type="Message")

    assert first.id == 42
    assert second.id == 43
    assert reader._remaining() == 0
