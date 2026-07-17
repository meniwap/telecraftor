from __future__ import annotations

from telecraft.tl.codec import TLWriter, loads
from telecraft.tl.generated.types import (
    MessageMediaPoll,
    Poll,
    PollAnswer,
    PollAnswerVoters,
    PollResults,
    TextWithEntities,
)


def _sample_text(text: str) -> TextWithEntities:
    return TextWithEntities(text=text.encode("utf-8"), entities=[])


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
                text=_sample_text("Answer"),
                option=b"A",
            )
        ],
    )

    # Next object starts immediately with pollResults constructor.
    writer.write_object(
        PollResults(
            flags=0,
            min=False,
            results=None,
            total_voters=None,
            recent_voters=None,
            solution=None,
            solution_entities=None,
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
            question=_sample_text("Synthetic question"),
            answers=[PollAnswer(text=_sample_text("Synthetic answer"), option=b"A")],
            close_period=None,
            close_date=None,
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
