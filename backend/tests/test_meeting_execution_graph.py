import pytest

from app.agents import meeting_execution_graph
from app.agents.meeting_execution_graph import (
    _route_from_unconfirmed_items,
    inspect_meeting_input_quality,
    normalize_clarifications,
)
from app.schemas.analysis import ExtractedActionItem, MeetingDraftExtraction


def test_input_quality_rejects_empty_content() -> None:
    status, reason = inspect_meeting_input_quality("   ")

    assert status == "needs_clarification"
    assert reason == "meeting raw content is empty"


def test_input_quality_rejects_too_short_content() -> None:
    status, reason = inspect_meeting_input_quality("只说了要跟进")

    assert status == "needs_clarification"
    assert reason == "meeting raw content is too short"


def test_input_quality_accepts_readable_meeting_notes() -> None:
    content = (
        "本次会议确认支付回调接口本周完成联调，张三负责签名校验，"
        "李四负责失败重试和日志告警。下周三前完成测试并同步风险。"
    )

    status, reason = inspect_meeting_input_quality(content)

    assert status == "ok"
    assert reason is None


@pytest.mark.asyncio
async def test_graph_normalize_clarifications_adds_missing_owner_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_update_workflow(*args, **kwargs) -> None:  # noqa: ANN002, ANN003
        return None

    monkeypatch.setattr(meeting_execution_graph, "_update_workflow", fake_update_workflow)
    extraction = MeetingDraftExtraction(
        decision_summary="确认接口联调安排",
        action_items=[
            ExtractedActionItem(
                title="完成后端接口联调",
                owner_name=None,
                deadline_text="本周五",
            )
        ],
        unconfirmed_items=[],
    )

    result = await normalize_clarifications(
        {
            "meeting_id": "meeting-1",
            "workflow_run_id": "workflow-1",
            "extraction": extraction,
        }
    )

    normalized = result["extraction"]
    assert result["current_step"] == "normalize_clarifications"
    assert result["unconfirmed_count"] == 1
    assert normalized.unconfirmed_items[0].question == "待办「完成后端接口联调」的负责人是谁？"


def test_graph_routes_to_clarification_when_unconfirmed_count_exists() -> None:
    next_node = _route_from_unconfirmed_items(
        {
            "unconfirmed_count": 1,
            "resume_action": "start",
        }
    )

    assert next_node == "wait_for_clarification"
