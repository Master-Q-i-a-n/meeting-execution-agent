from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import DbSession
from app.core.logger import get_logger
from app.core.redis_client import check_redis_connection_sync
from app.models.analysis import ActionItem, AnalysisDraft
from app.models.workflow import WorkflowRun
from app.schemas.analysis import (
    ActionItemDraftResponse,
    ActionItemDraftUpdateRequest,
    AnalysisDraftResponse,
    DraftConfirmationResponse,
    DraftConfirmationSnapshotResponse,
    DraftDispatchResponse,
    DraftStatusUpdateRequest,
)
from app.services.execution_drafts import (
    ExecutionDraftError,
    confirm_execution_draft,
    transition_execution_draft,
    update_action_item_draft,
)
from app.services.task_dispatch import ExternalTaskDispatchError, ensure_draft_can_dispatch
from app.workers.tasks import dispatch_analysis_draft_task

logger = get_logger(__name__)
router = APIRouter(tags=["analysis-drafts"])


async def _load_analysis_draft_detail(
    db: AsyncSession,
    draft_id: str,
) -> AnalysisDraft | None:
    """按草稿 ID 取完整审核上下文，供编辑、确认和派发复用。"""
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
    """人工审核时修改执行待办。"""
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
    logger.info(
        "待办草稿编辑完成 draft_id=%s action_item_id=%s",
        draft_id,
        action_item_id,
    )
    return ActionItemDraftResponse.from_model(item)


@router.post(
    "/analysis-drafts/{draft_id}/confirm",
    response_model=DraftConfirmationResponse,
)
async def confirm_analysis_draft(
    draft_id: str,
    db: DbSession,
):
    """用户确认执行草稿并自动投递派发任务。"""
    draft = await _load_analysis_draft_detail(db, draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="analysis draft not found")

    try:
        snapshot = confirm_execution_draft(draft)
    except ExecutionDraftError as exc:
        logger.warning("执行草稿确认被拒绝 draft_id=%s error=%s", draft_id, exc)
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    db.add(snapshot)
    await db.commit()
    await db.refresh(draft, attribute_names=["updated_at"])
    await db.refresh(snapshot)
    dispatch = await _queue_analysis_draft_dispatch(
        db=db,
        draft=draft,
        trigger="confirm",
    )
    logger.info(
        "执行草稿确认完成 draft_id=%s snapshot_id=%s dispatch_workflow_run_id=%s",
        draft.id,
        snapshot.id,
        dispatch.workflow_run_id,
    )
    return DraftConfirmationResponse(
        draft=AnalysisDraftResponse.from_model(draft),
        snapshot=DraftConfirmationSnapshotResponse.from_model(snapshot),
        dispatch=dispatch,
    )


@router.post(
    "/analysis-drafts/{draft_id}/dispatch",
    response_model=DraftDispatchResponse,
)
async def dispatch_analysis_draft(
    draft_id: str,
    db: DbSession,
):
    """手动派发入口用于调试和失败后的幂等重派。"""
    draft = await _load_analysis_draft_detail(db, draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="analysis draft not found")
    return await _queue_analysis_draft_dispatch(db=db, draft=draft, trigger="api")


@router.patch(
    "/analysis-drafts/{draft_id}/status",
    response_model=AnalysisDraftResponse,
)
async def update_analysis_draft_status(
    draft_id: str,
    request: DraftStatusUpdateRequest,
    db: DbSession,
):
    """按状态机推进确认后的执行草稿。"""
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


async def _queue_analysis_draft_dispatch(
    *,
    db: AsyncSession,
    draft: AnalysisDraft,
    trigger: str,
) -> DraftDispatchResponse:
    """创建派发 workflow，再把 Linear 创建任务交给 Celery worker。"""
    try:
        ensure_draft_can_dispatch(draft)
    except ExternalTaskDispatchError as exc:
        logger.warning("草稿派发被拒绝 draft_id=%s trigger=%s error=%s", draft.id, trigger, exc)
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    workflow_run = WorkflowRun(
        meeting_id=draft.meeting_id,
        workflow_type="external_task_dispatch",
        current_node="queue",
        status="pending",
        payload_json={"trigger": trigger, "provider": "linear", "draft_id": draft.id},
    )
    db.add(workflow_run)
    await db.commit()
    await db.refresh(workflow_run)
    logger.info(
        "草稿派发任务准备投递 draft_id=%s workflow_run_id=%s trigger=%s",
        draft.id,
        workflow_run.id,
        trigger,
    )

    try:
        check_redis_connection_sync()
        task = dispatch_analysis_draft_task.delay(draft.id, workflow_run.id)
    except Exception as exc:
        workflow_run.status = "failed"
        workflow_run.current_node = "queue"
        workflow_run.error_message = f"Celery publish failed: {exc}"
        await db.commit()
        logger.exception(
            "草稿派发任务投递失败 draft_id=%s workflow_run_id=%s error=%s",
            draft.id,
            workflow_run.id,
            exc,
        )
        raise HTTPException(status_code=503, detail=f"Celery publish failed: {exc}") from exc

    logger.info(
        "草稿派发任务投递成功 draft_id=%s workflow_run_id=%s task_id=%s",
        draft.id,
        workflow_run.id,
        task.id,
    )
    return DraftDispatchResponse(
        draft_id=draft.id,
        workflow_run_id=workflow_run.id,
        task_id=task.id,
        status=task.status,
    )
