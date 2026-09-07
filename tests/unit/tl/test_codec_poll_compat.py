from __future__ import annotations

import pytest

from telecraft.tl.codec import TLWriter, UnknownConstructorError, loads
from telecraft.tl.generated.types import (
    MessageMediaEmpty,
    MessageMediaPoll,
    Poll,
    PollAnswer,
    PollAnswerVoters,
    PollResults,
    TextWithEntities,
)


def _sample_text(text: str) -> TextWithEntities:
    return TextWithEntities(text=text.encode("utf-8"), entities=[])


def test_codec__poll_message__roundtrips_layer_228_fields() -> None:
    media = MessageMediaPoll(
        flags=0,
        poll=Poll(
            id=777,
            flags=0,
            closed=False,
            public_voters=False,
            multiple_choice=False,
            quiz=False,
            open_answers=True,
            revoting_disabled=False,
            shuffle_answers=True,
            hide_results_until_close=False,
            creator=True,
            subscribers_only=False,
            question=_sample_text("Layer 228 question"),
            answers=[
                PollAnswer(
                    flags=0,
                    text=_sample_text("Layer 228 answer"),
                    option=b"A",
                    media=None,
                    added_by=None,
                    date=None,
                )
            ],
            close_period=None,
            close_date=None,
            countries_iso2=["IL"],
            hash=123456,
        ),
        results=PollResults(
            flags=0,
            min=False,
            has_unread_votes=True,
            can_view_stats=True,
            results=None,
            total_voters=None,
            recent_voters=None,
            solution=None,
            solution_entities=None,
            solution_media=None,
        ),
        attached_media=MessageMediaEmpty(),
    )
    writer = TLWriter()
    writer.write_object(media)

    decoded = loads(writer.to_bytes())

    assert decoded.flags == 1
    assert decoded.poll.open_answers is True
    assert decoded.poll.shuffle_answers is True
    assert decoded.poll.creator is True
    assert decoded.poll.countries_iso2 == [b"IL"]
    assert decoded.poll.hash == 123456
    assert decoded.results.has_unread_votes is True
    assert decoded.results.can_view_stats is True
    assert decoded.attached_media.TL_NAME == "messageMediaEmpty"


def test_codec__poll_message__does_not_misconsume_poll_results_constructor() -> None:
    writer = TLWriter()
    writer.write_int(MessageMediaPoll.TL_ID)

    # Craft a poll where flags say close_date exists, but close_date is intentionally omitted.
    writer.write_int(Poll.TL_ID)
    writer.write_long(777)
    writer.write_int(1 << 5)
    writer.write_object(_sample_text("Question"))
    writer.write_value(
        "Vector<PollAnswer>",
        [
            PollAnswer(
                flags=0,
                text=_sample_text("Answer"),
                option=b"A",
                media=None,
                added_by=None,
                date=None,
            )
        ],
    )

    # Next object starts immediately with pollResults constructor.
    writer.write_object(
        PollResults(
            flags=0,
            min=False,
            has_unread_votes=False,
            can_view_stats=False,
            results=None,
            total_voters=None,
            recent_voters=None,
            solution=None,
            solution_entities=None,
            solution_media=None,
        )
    )

    media = loads(writer.to_bytes())
    assert getattr(media, "TL_NAME", "") == "messageMediaPoll"
    assert media.poll.close_date is None
    assert int(media.poll.flags) & (1 << 5) == 0
    assert getattr(media.results, "TL_NAME", "") == "pollResults"


def test_codec__poll_results__bare_fallback_when_boxed_fails() -> None:
    # Synthetic regression payload: pollResults is deliberately encoded bare
    # (without its constructor) after a normal messageMediaPoll. The original
    # regression was captured from a live account; the full payload contained
    # unrelated Telegram data and does not belong in a source distribution.
    writer = TLWriter()
    writer.write_int(MessageMediaPoll.TL_ID)
    writer.write_object(
        Poll(
            id=777,
            flags=0,
            closed=False,
            public_voters=False,
            multiple_choice=False,
            quiz=False,
            open_answers=False,
            revoting_disabled=False,
            shuffle_answers=False,
            hide_results_until_close=False,
            creator=False,
            subscribers_only=False,
            question=_sample_text("Synthetic question"),
            answers=[
                PollAnswer(
                    flags=0,
                    text=_sample_text("Synthetic answer"),
                    option=b"A",
                    media=None,
                    added_by=None,
                    date=None,
                )
            ],
            close_period=None,
            close_date=None,
            countries_iso2=None,
            hash=0,
        )
    )
    writer.write_int(6)  # results + total_voters; intentionally no PollResults.TL_ID
    writer.write_value(
        "Vector<PollAnswerVoters>",
        [
            PollAnswerVoters(
                flags=0,
                chosen=False,
                correct=False,
                option=b"A",
                voters=3,
                recent_voters=[],
            )
        ],
    )
    writer.write_int(3)

    decoded = loads(writer.to_bytes())

    assert getattr(decoded, "TL_NAME", "") == "messageMediaPoll"
    assert getattr(decoded.results, "TL_NAME", "") == "pollResults"
    assert int(decoded.results.flags) == 6
    assert decoded.results.total_voters == 3
    assert decoded.results.results[0].option == b"A"


def test_codec__poll_results__nested_unknown_constructor_is_not_bare_fallback() -> None:
    writer = TLWriter()
    writer.write_int(MessageMediaPoll.TL_ID)
    writer.write_object(
        Poll(
            id=777,
            flags=0,
            closed=False,
            public_voters=False,
            multiple_choice=False,
            quiz=False,
            open_answers=False,
            revoting_disabled=False,
            shuffle_answers=False,
            hide_results_until_close=False,
            creator=False,
            subscribers_only=False,
            question=_sample_text("Synthetic question"),
            answers=[],
            close_period=None,
            close_date=None,
            countries_iso2=None,
            hash=0,
        )
    )
    writer.write_uint(0x12345678)

    with pytest.raises(UnknownConstructorError) as raised:
        loads(writer.to_bytes())

    assert raised.value.constructor_id == 0x12345678
    assert raised.value.expected_type == "PollResults"
    assert raised.value.path == "root.results"
