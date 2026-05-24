from datetime import datetime

import pytest

from app.models.analysis import ActionItem, AnalysisDraft
from app.services.execution_drafts import (
    ExecutionDraftError,
    confirm_execution_draft,
    transition_execution_draft,
    update_action_item_draft,
)


def _build_draft(*, status: str = "draft") -> AnalysisDraft:
    draft = AnalysisDraft(
        id="draft-1",
        meeting_id="meeting-1",
        status=status,
        model_name="qwen-plus",
        prompt_version="meeting-draft-v1",
        decision_summary="先完成支付联调。",
        raw_result_json={
            "decision_summary": "先完成支付联调。",
            "action_items": [{"title": "联调支付回调", "owner_name": None}],
        },
    )
    draft.action_items = [
        ActionItem(
            id="action-1",
            title="联调支付回调",
            description="检查回调签名",
            owner_name=None,
            order_index=0,
        )
    ]
    draft.decisions = []
    draft.risk_items = []
    draft.unconfirmed_items = []
    return draft


def test_action_item_draft_can_be_edited_before_confirmation() -> None:
    draft = _build_draft()
    item = draft.action_items[0]
    due_at = datetime(2026, 5, 29, 18, 0)

    update_action_item_draft(
        draft=draft,
        item=item,
        updates={
            "title": "完成支付回调联调",
            "owner_name": "张三",
            "deadline_text": "本周五下班前",
            "due_at": due_at,
            "description": "补齐签名校验和失败重试",
            "priority": "high",
        },
    )

    assert item.title == "完成支付回调联调"
    assert item.owner_name == "张三"
    assert item.due_at == due_at
    assert item.priority == "high"


def test_confirmed_action_item_draft_cannot_be_edited() -> None:
    draft = _build_draft(status="confirmed")

    with pytest.raises(ExecutionDraftError, match="only draft"):
        update_action_item_draft(
            draft=draft,
            item=draft.action_items[0],
            updates={"owner_name": "张三"},
        )


def test_confirm_execution_draft_saves_agent_and_human_snapshots() -> None:
    draft = _build_draft()
    draft.action_items[0].owner_name = "张三"
    draft.action_items[0].priority = "high"

    snapshot = confirm_execution_draft(draft)

    assert draft.status == "confirmed"
    assert draft.action_items[0].status == "confirmed"
    assert snapshot.agent_suggestion_json["action_items"][0]["owner_name"] is None
    assert snapshot.confirmed_draft_json["action_items"][0]["owner_name"] == "张三"
    assert snapshot.confirmed_draft_json["action_items"][0]["priority"] == "high"


def test_execution_draft_status_machine_rejects_skipped_steps() -> None:
    draft = _build_draft()

    with pytest.raises(ExecutionDraftError, match="draft status cannot transition"):
        transition_execution_draft(draft, "completed")

    transition_execution_draft(draft, "confirmed")
    transition_execution_draft(draft, "dispatching")
    transition_execution_draft(draft, "completed")

    assert draft.status == "completed"
