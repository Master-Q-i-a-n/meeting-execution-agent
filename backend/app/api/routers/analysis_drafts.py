from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import DbSession
from app.core.logger import get_logger
from app.models.analysis import ActionItem, AnalysisDraft
from app.models.workflow import WorkflowRun
from app.schemas.analysis import (
    ActionItemDraftResponse,
    ActionItemDraftUpdateRequest,
    AnalysisDraftResponse,
    DraftStatusUpdateRequest,
)
from app.schemas.workflow import WorkflowContinueResponse
from app.services.execution_drafts import (
    ExecutionDraftError,
    transition_execution_draft,
    update_action_item_draft,
)
from app.services.workflow_resume import WorkflowResumeError, queue_workflow_resume

logger = get_logger(__name__)
router = APIRouter(tags=["analysis-drafts"])


async def _load_analysis_draft_detail(
    db: AsyncSession,
    draft_id: str,
) -> AnalysisDraft | None:
    """按草稿 ID 取完整审核上下文，供编辑、确认和重派复用。"""
    statement = (
        select(AnalysisDraft)
        .options(
            selectinload(AnalysisDraft.decisions),
            selectinload(AnalysisDraft.action_items).selectinload(
                ActionItem.external_task_mappings
            ),
            selectinload(AnalysisDraft.risk_items),
            selectinload(AnalysisDraft.unconfirmed_items),
        )
        .where(AnalysisDraft.id == draft_id)
    )
    result = await db.execute(statement)
    return result.scalars().first()


@router.patch(
    "/analysis-drafts/{draft_id}/action-items/{action_item_id}",
    response_model=ActionItemDraftResponse,
)
async def edit_analysis_draft_action_item(
    draft_id: str,
    action_item_id: str,
    request: ActionItemDraftUpdateRequest,
    db: DbSession,
):
    """人工审核时修改执行待办；编辑本身不推进 LangGraph。"""
    draft = await _load_analysis_draft_detail(db, draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="analysis draft not found")

    item = next((item for item in draft.action_items if item.id == action_item_id), None)
    if item is None:
        raise HTTPException(status_code=404, detail="action item not found")

    try:
        update_action_item_draft(
            draft=draft,
            item=item,
            updates=request.model_dump(exclude_unset=True),
        )
    except ExecutionDraftError as exc:
        logger.warning(
            "待办草稿编辑被拒绝 draft_id=%s action_item_id=%s error=%s",
            draft_id,
            action_item_id,
            exc,
        )
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    await db.commit()
    logger.info("待办草稿编辑完成 draft_id=%s action_item_id=%s", draft_id, action_item_id)
    return ActionItemDraftResponse.from_model(item)


@router.post(
    "/analysis-drafts/{draft_id}/confirm",
    response_model=WorkflowContinueResponse,
)
async def confirm_analysis_draft(
    draft_id: str,
    db: DbSession,
):
    """兼容确认入口：恢复等待确认的同一个会议执行工作流。"""
    draft = await _load_analysis_draft_detail(db, draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="analysis draft not found")

    try:
        workflow = await _find_or_create_confirmation_workflow_for_draft(db=db, draft=draft)
        response = await queue_workflow_resume(
            db=db,
            workflow=workflow,
            action="confirm_draft",
        )
    except LookupError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except WorkflowResumeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        await db.commit()
        raise HTTPException(status_code=503, detail=f"Celery publish failed: {exc}") from exc

    await db.commit()
    logger.info(
        "草稿确认恢复任务已投递 draft_id=%s workflow_run_id=%s",
        draft.id,
        response.workflow_run_id,
    )
    return response


@router.post(
    "/analysis-drafts/{draft_id}/dispatch",
    response_model=WorkflowContinueResponse,
)
async def dispatch_analysis_draft(
    draft_id: str,
    db: DbSession,
):
    """兼容手动重派入口：恢复失败的同一个会议执行工作流。"""
    draft = await _load_analysis_draft_detail(db, draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="analysis draft not found")

    try:
        workflow = await _find_resume_workflow_for_draft(
            db=db,
            draft=draft,
            allowed_statuses={"failed"},
        )
        response = await queue_workflow_resume(
            db=db,
            workflow=workflow,
            action="retry_dispatch",
        )
    except LookupError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except WorkflowResumeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        await db.commit()
        raise HTTPException(status_code=503, detail=f"Celery publish failed: {exc}") from exc

    await db.commit()
    logger.info(
        "草稿重派恢复任务已投递 draft_id=%s workflow_run_id=%s",
        draft.id,
        response.workflow_run_id,
    )
    return response


@router.patch(
    "/analysis-drafts/{draft_id}/status",
    response_model=AnalysisDraftResponse,
)
async def update_analysis_draft_status(
    draft_id: str,
    request: DraftStatusUpdateRequest,
    db: DbSession,
):
    """保留手动状态推进接口，主要用于调试或外部派发后的兼容场景。"""
    draft = await _load_analysis_draft_detail(db, draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="analysis draft not found")

    try:
        transition_execution_draft(draft, request.status)
    except ExecutionDraftError as exc:
        logger.warning(
            "执行草稿状态推进被拒绝 draft_id=%s target_status=%s error=%s",
            draft_id,
            request.status,
            exc,
        )
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    await db.commit()
    await db.refresh(draft, attribute_names=["updated_at"])
    logger.info("执行草稿状态推进完成 draft_id=%s status=%s", draft_id, request.status)
    return AnalysisDraftResponse.from_model(draft)


async def _find_resume_workflow_for_draft(
    *,
    db: AsyncSession,
    draft: AnalysisDraft,
    allowed_statuses: set[str],
) -> WorkflowRun:
    """从 workflow_runs 找回挂住当前 draft 的会议执行流程。"""
    statement = (
        select(WorkflowRun)
        .where(
            WorkflowRun.meeting_id == draft.meeting_id,
            WorkflowRun.status.in_(allowed_statuses),
        )
        .order_by(WorkflowRun.created_at.desc())
    )
    workflows = (await db.execute(statement)).scalars().all()
    for workflow in workflows:
        if (workflow.payload_json or {}).get("draft_id") == draft.id:
            return workflow
    raise LookupError("matching waiting workflow not found for draft")


async def _find_or_create_confirmation_workflow_for_draft(
    *,
    db: AsyncSession,
    draft: AnalysisDraft,
) -> WorkflowRun:
    """找到等待确认的 workflow；历史草稿缺少等待节点时，创建兼容恢复入口。"""
    try:
        return await _find_resume_workflow_for_draft(
            db=db,
            draft=draft,
            allowed_statuses={"waiting_confirmation"},
        )
    except LookupError:
        pass

    if draft.status != "draft":
        raise LookupError("matching waiting workflow not found for draft")

    latest_workflow = await db.scalar(
        select(WorkflowRun)
        .where(WorkflowRun.meeting_id == draft.meeting_id)
        .order_by(WorkflowRun.created_at.desc())
        .limit(1)
    )
    # 旧版分析流程生成草稿后会直接 completed，没有 wait_for_confirmation。
    # 这里补一条等待确认记录，让旧草稿也能进入新的 confirm_draft -> dispatch_tasks 链路。
    workflow = WorkflowRun(
        meeting_id=draft.meeting_id,
        workflow_type="meeting_execution",
        current_node="wait_for_confirmation",
        status="waiting_confirmation",
        payload_json={
            "trigger": "confirm_compat",
            "draft_id": draft.id,
            "resume_action": "confirm_draft",
            "compat_from_workflow_run_id": (
                latest_workflow.id if latest_workflow is not None else None
            ),
        },
    )
    db.add(workflow)
    await db.flush()
    logger.info(
        "旧草稿缺少等待确认 workflow，已创建兼容恢复入口 draft_id=%s workflow_run_id=%s",
        draft.id,
        workflow.id,
    )
    return workflow
