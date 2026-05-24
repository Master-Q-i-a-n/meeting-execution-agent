from datetime import datetime

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.dependencies import DbSession
from app.core.logger import get_logger
from app.models.analysis import ActionItem, AnalysisDraft
from app.schemas.analysis import ActionItemBoardResponse, ActionItemDraftResponse
from app.schemas.reminder import ActionItemStatusUpdateRequest

logger = get_logger(__name__)
router = APIRouter(tags=["action-items"])


@router.patch(
    "/action-items/{action_item_id}/status",
    response_model=ActionItemDraftResponse,
)
async def update_action_item_status(
    action_item_id: str,
    request: ActionItemStatusUpdateRequest,
    db: DbSession,
):
    """手动把待办标记为完成或取消。"""
    statement = (
        select(ActionItem)
        .options(selectinload(ActionItem.external_task_mappings))
        .where(ActionItem.id == action_item_id)
    )
    item = (await db.execute(statement)).scalars().first()
    if item is None:
        raise HTTPException(status_code=404, detail="action item not found")

    item.status = request.status
    await db.commit()
    logger.info(
        "待办状态更新完成 action_item_id=%s status=%s",
        action_item_id,
        request.status,
    )
    return ActionItemDraftResponse.from_model(item)


@router.get("/action-items", response_model=list[ActionItemBoardResponse])
async def list_action_items(
    db: DbSession,
    status: str | None = None,
    owner_name: str | None = None,
    due_before: datetime | None = None,
):
    """执行看板查询待办列表，可按状态、负责人和截止时间过滤。"""
    statement = (
        select(ActionItem)
        .join(AnalysisDraft, ActionItem.analysis_draft_id == AnalysisDraft.id)
        .options(
            selectinload(ActionItem.analysis_draft),
            selectinload(ActionItem.external_task_mappings),
        )
        .order_by(ActionItem.due_at.is_(None), ActionItem.due_at, ActionItem.created_at.desc())
    )
    if status:
        statement = statement.where(ActionItem.status == status)
    if owner_name:
        statement = statement.where(ActionItem.owner_name == owner_name)
    if due_before:
        statement = statement.where(ActionItem.due_at <= due_before)

    action_items = (await db.execute(statement)).scalars().all()
    return [ActionItemBoardResponse.from_model(item) for item in action_items]
