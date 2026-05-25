from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import get_logger
from app.core.redis_client import check_redis_connection_sync
from app.models.workflow import WorkflowRun
from app.schemas.workflow import WorkflowContinueResponse, WorkflowResumeAction
from app.workers.tasks import resume_meeting_execution_workflow_task

logger = get_logger(__name__)

ALLOWED_RESUME_STATUS_BY_ACTION: dict[WorkflowResumeAction, set[str]] = {
    "retry_input": {"waiting_input_clarification"},
    "retry_extraction": {"waiting_clarification"},
    "force_continue": {"waiting_clarification"},
    "confirm_draft": {"waiting_confirmation"},
    "retry_dispatch": {"failed"},
}


class WorkflowResumeError(RuntimeError):
    """当前工作流状态不允许执行恢复动作。"""


def ensure_workflow_can_resume(
    workflow: WorkflowRun,
    action: WorkflowResumeAction,
) -> None:
    allowed_statuses = ALLOWED_RESUME_STATUS_BY_ACTION[action]
    if workflow.status not in allowed_statuses:
        raise WorkflowResumeError(
            f"workflow status {workflow.status} cannot resume with action {action}"
        )
    if workflow.meeting_id is None:
        raise WorkflowResumeError("workflow is not attached to a meeting")


async def queue_workflow_resume(
    *,
    db: AsyncSession,
    workflow: WorkflowRun,
    action: WorkflowResumeAction,
) -> WorkflowContinueResponse:
    """把等待中的会议执行工作流重新投递给 Celery。

    这里不直接跑 LangGraph，避免 FastAPI 请求被 LLM、Qdrant 或 Linear 阻塞。
    """
    ensure_workflow_can_resume(workflow, action)
    workflow.status = "pending"
    workflow.current_node = "queue_resume"
    workflow.error_message = None
    workflow.payload_json = {
        **(workflow.payload_json or {}),
        "resume_action": action,
    }
    # 先提交等待状态，再投递 Celery，避免 worker 启动太快时读到旧 workflow。
    await db.commit()
    await db.refresh(workflow)

    try:
        check_redis_connection_sync()
        task = resume_meeting_execution_workflow_task.delay(workflow.id, action)
    except Exception as exc:
        workflow.status = "failed"
        workflow.current_node = "queue_resume"
        workflow.error_message = f"Celery publish failed: {exc}"
        logger.exception(
            "恢复会议工作流投递失败 workflow_run_id=%s action=%s error=%s",
            workflow.id,
            action,
            exc,
        )
        await db.commit()
        raise

    logger.info(
        "恢复会议工作流投递成功 workflow_run_id=%s action=%s task_id=%s",
        workflow.id,
        action,
        task.id,
    )
    return WorkflowContinueResponse(
        workflow_run_id=workflow.id,
        task_id=task.id,
        action=action,
        status=task.status,
    )
