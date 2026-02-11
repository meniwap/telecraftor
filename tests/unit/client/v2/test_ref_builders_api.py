from __future__ import annotations

from telecraft.client import (
    ChatlistRef,
    DocumentRef,
    NotifyTarget,
    PrivacyRuleBuilder,
    StickerSetRef,
)


def test_ref_builders__stickersetref_short_name__returns_expected_shape() -> None:
    ref = StickerSetRef.short_name("telecraft")
    assert ref.kind == "short_name"
    assert ref.short_name_value == "telecraft"


def test_ref_builders__documentref_from_parts__returns_expected_shape() -> None:
    doc = DocumentRef.from_parts(10, 20, b"abc")
    assert doc.doc_id == 10
    assert doc.access_hash == 20
    assert doc.file_reference == b"abc"


def test_ref_builders__notifytarget_forum_topic__returns_expected_shape() -> None:
    target = NotifyTarget.forum_topic("channel:1", 15)
    assert target.kind == "forum_topic"
    assert target.peer == "channel:1"
    assert target.top_msg_id == 15


def test_ref_builders__chatlistref_by_filter__returns_expected_shape() -> None:
    ref = ChatlistRef.by_filter(7)
    assert ref.filter_id == 7
    assert ref.to_input().filter_id == 7


def test_ref_builders__privacyrulebuilder_allow_all__returns_expected_shape() -> None:
    rule = PrivacyRuleBuilder.allow_all()
    assert rule is not None
