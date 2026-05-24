from app.schemas.analysis import MeetingDraftExtraction


def test_meeting_draft_extraction_validates_action_item_deadline() -> None:
    """结构化草稿会把标准 due_at 转为 datetime，保留截止时间原文。"""
    extraction = MeetingDraftExtraction.model_validate(
        {
            "decision_summary": "先完成后端分析链路。",
            "decisions": [{"summary": "阶段二接百炼解析。"}],
            "action_items": [
                {
                    "title": "完成迁移",
                    "owner_name": "张三",
                    "deadline_text": "下周三",
                    "due_at": "2026-05-27T00:00:00",
                    "confidence": 0.88,
                }
            ],
            "risk_items": [{"title": "模型可能遗漏待办。"}],
            "unconfirmed_items": [{"question": "李四是否负责评测样例？"}],
        }
    )

    assert extraction.action_items[0].deadline_text == "下周三"
    assert extraction.action_items[0].due_at is not None
    assert extraction.action_items[0].due_at.year == 2026


def test_meeting_draft_extraction_allows_empty_optional_lists() -> None:
    """会议没有风险或待办时也能得到合法草稿。"""
    extraction = MeetingDraftExtraction.model_validate({"decision_summary": "同步信息。"})

    assert extraction.decisions == []
    assert extraction.action_items == []
    assert extraction.risk_items == []
    assert extraction.unconfirmed_items == []
