from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import get_logger
from app.models.workflow import WorkflowRun

logger = get_logger(__name__)

WAITING_WORKFLOW_STATUSES = {
    "waiting_input_clarification",
    "waiting_clarification",
    "waiting_confirmation",
}


async def cancel_waiting_meeting_workflows(
    *,
    db: AsyncSession,
    meeting_id: str,
    superseded_by_workflow_run_id: str,
    reason: str,
) -> int:
    """重新分析同一会议时，把旧的等待流程标记为已取消。

    workflow_runs 是执行历史，不直接删除；但旧 draft 被新分析替换后，
    原来停在 wait_for_confirmation 的流程已经不能继续确认，需要从前端 Trace 中
    显示成 cancelled，避免看起来还有一个未完成任务。
    """
    statement = select(WorkflowRun).where(
        WorkflowRun.meeting_id == meeting_id,
        WorkflowRun.status.in_(WAITING_WORKFLOW_STATUSES),
    )
    workflows = (await db.execute(statement)).scalars().all()
    cancelled_count = 0
    for workflow in workflows:
        if workflow.id == superseded_by_workflow_run_id:
            continue
        workflow.status = "cancelled"
        workflow.current_node = "superseded"
        workflow.error_message = None
        workflow.payload_json = {
            **(workflow.payload_json or {}),
            "superseded_by_workflow_run_id": superseded_by_workflow_run_id,
            "superseded_reason": reason,
        }
        cancelled_count += 1

    if cancelled_count:
        logger.info(
            "已取消同一会议的旧等待 workflow meeting_id=%s superseded_by=%s count=%s",
            meeting_id,
            superseded_by_workflow_run_id,
            cancelled_count,
        )
    return cancelled_count
