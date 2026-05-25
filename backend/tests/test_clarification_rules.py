from app.schemas.analysis import (
    ExtractedActionItem,
    ExtractedUnconfirmedItem,
    MeetingDraftExtraction,
)
from app.services.clarification_rules import normalize_meeting_clarifications


def _build_extraction(*, action_item: ExtractedActionItem) -> MeetingDraftExtraction:
    return MeetingDraftExtraction(
        decision_summary="确认接口联调安排",
        action_items=[action_item],
    )


def test_missing_owner_generates_owner_clarification() -> None:
    extraction = _build_extraction(
        action_item=ExtractedActionItem(
            title="完成后端接口联调",
            owner_name=None,
            deadline_text="本周五",
            source_excerpt="某人负责完成后端接口联调，本周五前完成。",
            confidence=0.8,
        )
    )

    normalized = normalize_meeting_clarifications(extraction)

    assert normalized.action_items[0].owner_name is None
    assert normalized.unconfirmed_items[0].question == "待办「完成后端接口联调」的负责人是谁？"


def test_placeholder_owner_is_normalized_and_generates_clarification() -> None:
    extraction = _build_extraction(
        action_item=ExtractedActionItem(
            title="准备测试会议纪要",
            owner_name="某人",
            deadline_text="下周三",
        )
    )

    normalized = normalize_meeting_clarifications(extraction)

    assert normalized.action_items[0].owner_name is None
    assert [item.question for item in normalized.unconfirmed_items] == [
        "待办「准备测试会议纪要」的负责人是谁？"
    ]


def test_missing_deadline_generates_deadline_clarification() -> None:
    extraction = _build_extraction(
        action_item=ExtractedActionItem(
            title="补齐签名校验",
            owner_name="张三",
            deadline_text=None,
            due_at=None,
        )
    )

    normalized = normalize_meeting_clarifications(extraction)

    assert normalized.action_items[0].owner_name == "张三"
    assert normalized.unconfirmed_items[0].question == "待办「补齐签名校验」的截止时间是什么？"


def test_blank_deadline_text_is_treated_as_missing() -> None:
    extraction = _build_extraction(
        action_item=ExtractedActionItem(
            title="同步上线风险",
            owner_name="李四",
            deadline_text="   ",
            due_at=None,
        )
    )

    normalized = normalize_meeting_clarifications(extraction)

    assert normalized.action_items[0].deadline_text is None
    assert normalized.unconfirmed_items[0].question == "待办「同步上线风险」的截止时间是什么？"


def test_duplicate_clarification_is_not_added_twice() -> None:
    extraction = MeetingDraftExtraction(
        decision_summary="确认接口联调安排",
        action_items=[
            ExtractedActionItem(
                title="完成后端接口联调",
                owner_name=None,
                deadline_text="本周五",
                source_excerpt="某人负责完成后端接口联调，本周五前完成。",
            )
        ],
        unconfirmed_items=[
            ExtractedUnconfirmedItem(
                question="待办「完成后端接口联调」的负责人是谁？",
                source_excerpt="某人负责完成后端接口联调，本周五前完成。",
            )
        ],
    )

    normalized = normalize_meeting_clarifications(extraction)

    assert len(normalized.unconfirmed_items) == 1


def test_missing_owner_and_deadline_generate_two_questions() -> None:
    extraction = _build_extraction(
        action_item=ExtractedActionItem(
            title="完成部署脚本",
            owner_name="TBD",
            deadline_text=None,
            due_at=None,
        )
    )

    normalized = normalize_meeting_clarifications(extraction)

    assert [item.question for item in normalized.unconfirmed_items] == [
        "待办「完成部署脚本」的负责人是谁？",
        "待办「完成部署脚本」的截止时间是什么？",
    ]
