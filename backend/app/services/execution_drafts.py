from collections.abc import Mapping
from typing import Any

from app.core.logger import get_logger
from app.models.analysis import ActionItem, AnalysisDraft, DraftConfirmationSnapshot

logger = get_logger(__name__)

DRAFT_STATUS_TRANSITIONS = {
    "draft": {"confirmed"},
    "confirmed": {"dispatching"},
    "dispatching": {"completed", "failed"},
    "completed": set(),
    "failed": set(),
}


class ExecutionDraftError(ValueError):
    """执行草案不能完成当前人工审核操作。"""


def update_action_item_draft(
    *,
    draft: AnalysisDraft,
    item: ActionItem,
    updates: Mapping[str, Any],
) -> None:
    """把人工编辑结果写回待办草稿。"""
    if draft.status != "draft":
        raise ExecutionDraftError("only draft execution items can be edited")
    if "title" in updates and updates["title"] is None:
        raise ExecutionDraftError("action item title cannot be empty")

    # PATCH 只包含用户传来的字段，未传字段保持原值。
    for field, value in updates.items():
        setattr(item, field, value)
    logger.info(
        "执行草稿待办已更新 draft_id=%s action_item_id=%s fields=%s",
        draft.id,
        item.id,
        sorted(updates.keys()),
    )


def confirm_execution_draft(draft: AnalysisDraft) -> DraftConfirmationSnapshot:
    """确认执行草案，并保存模型建议和用户最终选择。"""
    # 先走状态机，避免非 draft 草稿被重复确认。
    transition_execution_draft(draft, "confirmed")
    # 草稿确认后，待办才正式进入执行阶段；提醒扫描只会扫描 confirmed/dispatched。
    for action_item in draft.action_items:
        action_item.status = "confirmed"
    logger.info(
        "执行草稿已确认 draft_id=%s action_item_count=%s",
        draft.id,
        len(draft.action_items),
    )
    return DraftConfirmationSnapshot(
        analysis_draft_id=draft.id,
        agent_suggestion_json=build_agent_suggestion_snapshot(draft),
        confirmed_draft_json=build_confirmed_draft_snapshot(draft),
    )


def transition_execution_draft(draft: AnalysisDraft, next_status: str) -> None:
    """按阶段三状态机推进执行草案。"""
    # 状态跳转集中在这里校验，API 和后台流程就不会各写一套规则。
    allowed_statuses = DRAFT_STATUS_TRANSITIONS.get(draft.status, set())
    if next_status not in allowed_statuses:
        raise ExecutionDraftError(
            f"draft status cannot transition from {draft.status} to {next_status}"
        )
    logger.info(
        "执行草稿状态流转 draft_id=%s from_status=%s to_status=%s",
        draft.id,
        draft.status,
        next_status,
    )
    draft.status = next_status


def build_agent_suggestion_snapshot(draft: AnalysisDraft) -> dict[str, Any]:
    """保留 Agent 原始建议，后续可和人工确认草案比较。"""
    # raw_result_json 是 LLM 结构化抽取后的原始建议，不受人工编辑影响。
    return dict(draft.raw_result_json)


def build_confirmed_draft_snapshot(draft: AnalysisDraft) -> dict[str, Any]:
    """把人工确认时的执行草案转成可落 JSON 的快照。"""
    # 快照取当前数据库对象值，因此能记录用户刚刚改过的负责人、截止时间等字段。
    return {
        "decision_summary": draft.decision_summary,
        "action_items": [
            {
                "id": item.id,
                "title": item.title,
                "description": item.description,
                "owner_name": item.owner_name,
                "deadline_text": item.deadline_text,
                "due_at": item.due_at.isoformat() if item.due_at is not None else None,
                "priority": item.priority,
                "source_excerpt": item.source_excerpt,
                "confidence": item.confidence,
            }
            for item in draft.action_items
        ],
    }
