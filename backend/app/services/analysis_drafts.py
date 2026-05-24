from typing import Any

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import get_logger
from app.models.analysis import ActionItem, AnalysisDraft, Decision, RiskItem, UnconfirmedItem
from app.models.meeting import Meeting
from app.schemas.analysis import MeetingDraftExtraction

logger = get_logger(__name__)


async def replace_current_analysis_draft(
    *,
    db: AsyncSession,
    meeting: Meeting,
    extraction: MeetingDraftExtraction,
    raw_result_json: dict[str, Any],
    model_name: str,
    prompt_version: str,
) -> AnalysisDraft:
    """用新的未确认草稿替换旧草稿。

    这个函数由工作流事务调用；只有 LLM 输出已经通过校验后才会走到这里。
    """
    logger.info(
        "替换当前分析草稿开始 meeting_id=%s decisions=%s action_items=%s risks=%s unconfirmed=%s",
        meeting.id,
        len(extraction.decisions),
        len(extraction.action_items),
        len(extraction.risk_items),
        len(extraction.unconfirmed_items),
    )
    # 只替换仍处于 draft 的旧草稿，已确认历史不能被新一次分析冲掉。
    await db.execute(
        delete(AnalysisDraft).where(
            AnalysisDraft.meeting_id == meeting.id,
            AnalysisDraft.status == "draft",
        )
    )

    draft = AnalysisDraft(
        meeting_id=meeting.id,
        status="draft",
        model_name=model_name,
        prompt_version=prompt_version,
        decision_summary=extraction.decision_summary,
        raw_result_json=raw_result_json,
    )
    # 下面把 Pydantic 抽取结果转成 ORM 子表记录。
    # 这些关系会随着 draft 一起 flush 到数据库。
    draft.decisions = [
        Decision(
            summary=item.summary,
            source_excerpt=item.source_excerpt,
            confidence=item.confidence,
            order_index=index,
        )
        for index, item in enumerate(extraction.decisions)
    ]
    draft.action_items = [
        ActionItem(
            title=item.title,
            description=item.description,
            owner_name=item.owner_name,
            deadline_text=item.deadline_text,
            due_at=item.due_at,
            source_excerpt=item.source_excerpt,
            confidence=item.confidence,
            order_index=index,
        )
        for index, item in enumerate(extraction.action_items)
    ]
    draft.risk_items = [
        RiskItem(
            title=item.title,
            description=item.description,
            source_excerpt=item.source_excerpt,
            confidence=item.confidence,
            order_index=index,
        )
        for index, item in enumerate(extraction.risk_items)
    ]
    draft.unconfirmed_items = [
        UnconfirmedItem(
            question=item.question,
            description=item.description,
            source_excerpt=item.source_excerpt,
            confidence=item.confidence,
            order_index=index,
        )
        for index, item in enumerate(extraction.unconfirmed_items)
    ]

    # 会议详情看到 draft 状态时，表示已有一版可供人工审核的草稿。
    meeting.status = "draft"
    db.add(draft)
    # flush 只把变更送到当前事务中，不在这里提交；
    # 提交由外层工作流统一控制，保证草稿主表和明细表一起成功或失败。
    await db.flush()
    logger.info(
        "替换当前分析草稿完成 meeting_id=%s draft_id=%s",
        meeting.id,
        draft.id,
    )
    return draft
