import asyncio

from app.agents.meeting_execution_graph import (
    MeetingExecutionState,
    resume_meeting_execution_workflow,
    run_meeting_execution_graph,
)
from app.core.logger import get_logger
from app.db.session import async_session_factory, close_database
from app.services.reminders import ReminderScanResult, scan_due_action_item_reminders
from app.services.task_dispatch import ExternalTaskDispatchResult, run_external_task_dispatch
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(name="debug.ping")
def debug_ping_task() -> dict[str, str]:
    """阶段一调试任务：证明 FastAPI -> Redis -> Celery 这条链路能跑通。"""
    return {"message": "pong"}


@celery_app.task(name="meetings.analyze")
def analyze_meeting_task(meeting_id: str, workflow_run_id: str) -> dict[str, str | None]:
    """Celery worker 独立跑会议分析图，避免 API 请求被 LLM 阻塞。"""
    logger.info(
        "Celery 会议分析任务开始 meeting_id=%s workflow_run_id=%s",
        meeting_id,
        workflow_run_id,
    )
    try:
        final_state = asyncio.run(
            _run_meeting_execution_with_database_cleanup(
                meeting_id=meeting_id,
                workflow_run_id=workflow_run_id,
            )
        )
    except Exception as exc:
        logger.exception(
            "Celery 会议分析任务失败 meeting_id=%s workflow_run_id=%s error=%s",
            meeting_id,
            workflow_run_id,
            exc,
        )
        raise
    logger.info(
        "Celery 会议分析任务完成 meeting_id=%s workflow_run_id=%s draft_id=%s status=%s",
        final_state["meeting_id"],
        final_state["workflow_run_id"],
        final_state["draft_id"],
        final_state["status"],
    )
    return {
        "meeting_id": final_state["meeting_id"],
        "workflow_run_id": final_state["workflow_run_id"],
        "draft_id": final_state["draft_id"],
        "status": final_state["status"],
    }


@celery_app.task(name="workflows.resume")
def resume_meeting_execution_workflow_task(
    workflow_run_id: str,
    resume_action: str,
) -> dict[str, str | None]:
    """恢复等待中的会议执行工作流，例如强制继续、确认草稿或重试派发。"""
    logger.info(
        "Celery 会议工作流恢复任务开始 workflow_run_id=%s resume_action=%s",
        workflow_run_id,
        resume_action,
    )
    try:
        final_state = asyncio.run(
            _resume_meeting_execution_workflow_with_database_cleanup(
                workflow_run_id=workflow_run_id,
                resume_action=resume_action,
            )
        )
    except Exception as exc:
        logger.exception(
            "Celery 会议工作流恢复任务失败 workflow_run_id=%s resume_action=%s error=%s",
            workflow_run_id,
            resume_action,
            exc,
        )
        raise
    logger.info(
        "Celery 会议工作流恢复任务完成 workflow_run_id=%s resume_action=%s status=%s",
        final_state["workflow_run_id"],
        final_state["resume_action"],
        final_state["status"],
    )
    return {
        "meeting_id": final_state["meeting_id"],
        "workflow_run_id": final_state["workflow_run_id"],
        "draft_id": final_state["draft_id"],
        "status": final_state["status"],
    }


async def _run_meeting_execution_with_database_cleanup(
    *,
    meeting_id: str,
    workflow_run_id: str,
) -> MeetingExecutionState:
    """在 Celery task 当前 event loop 里跑图，并释放异步数据库连接池。"""
    try:
        return await run_meeting_execution_graph(
            meeting_id=meeting_id,
            workflow_run_id=workflow_run_id,
        )
    finally:
        # Celery task 是同步入口；asyncio.run() 每次都会创建并关闭 event loop。
        # 必须在 loop 关闭前释放 aiomysql 连接，避免下次任务复用旧 loop 上的连接。
        await close_database()


async def _resume_meeting_execution_workflow_with_database_cleanup(
    *,
    workflow_run_id: str,
    resume_action: str,
) -> MeetingExecutionState:
    """在 Celery task 当前 event loop 中恢复 LangGraph，并释放异步连接池。"""
    try:
        return await resume_meeting_execution_workflow(
            workflow_run_id=workflow_run_id,
            resume_action=resume_action,  # type: ignore[arg-type]
        )
    finally:
        # resume 任务同样由 asyncio.run() 承载，必须在 loop 关闭前释放 aiomysql 连接。
        await close_database()


@celery_app.task(name="drafts.dispatch")
def dispatch_analysis_draft_task(
    draft_id: str,
    workflow_run_id: str,
) -> dict[str, str | int]:
    """Celery 独立创建 Linear 外部任务，避免确认接口阻塞等待网络调用。"""
    logger.info(
        "Celery 草稿派发任务开始 draft_id=%s workflow_run_id=%s",
        draft_id,
        workflow_run_id,
    )
    try:
        result = asyncio.run(
            _run_draft_dispatch_with_database_cleanup(
                draft_id=draft_id,
                workflow_run_id=workflow_run_id,
            )
        )
    except Exception as exc:
        logger.exception(
            "Celery 草稿派发任务失败 draft_id=%s workflow_run_id=%s error=%s",
            draft_id,
            workflow_run_id,
            exc,
        )
        raise
    logger.info(
        "Celery 草稿派发任务完成 draft_id=%s workflow_run_id=%s status=%s succeeded=%s skipped=%s failed=%s",
        result.draft_id,
        result.workflow_run_id,
        result.status,
        result.succeeded_count,
        result.skipped_count,
        result.failed_count,
    )
    return {
        "draft_id": result.draft_id,
        "workflow_run_id": result.workflow_run_id,
        "status": result.status,
        "succeeded_count": result.succeeded_count,
        "skipped_count": result.skipped_count,
        "failed_count": result.failed_count,
    }


async def _run_draft_dispatch_with_database_cleanup(
    *,
    draft_id: str,
    workflow_run_id: str,
) -> ExternalTaskDispatchResult:
    try:
        return await run_external_task_dispatch(
            draft_id=draft_id,
            workflow_run_id=workflow_run_id,
        )
    finally:
        # 派发任务同样由 asyncio.run() 承载，清连接池避免复用旧 event loop 的 aiomysql 连接。
        await close_database()


@celery_app.task(name="reminders.scan_due_action_items")
def scan_due_action_items_task() -> dict[str, int]:
    """Celery Beat 定时触发的应用内提醒扫描任务。"""
    logger.info("Celery 提醒扫描任务开始")
    try:
        result = asyncio.run(_run_reminder_scan_with_database_cleanup())
    except Exception as exc:
        logger.exception("Celery 提醒扫描任务失败 error=%s", exc)
        raise
    logger.info(
        "Celery 提醒扫描任务完成 created_count=%s skipped_count=%s",
        result.created_count,
        result.skipped_count,
    )
    return {
        "created_count": result.created_count,
        "skipped_count": result.skipped_count,
    }


async def _run_reminder_scan_with_database_cleanup() -> ReminderScanResult:
    try:
        async with async_session_factory() as db:
            result = await scan_due_action_item_reminders(db)
            await db.commit()
            return result
    finally:
        # Beat 任务也会反复创建 event loop，同样需要及时释放异步数据库连接池。
        await close_database()
