from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.agents.bootstrap_graph import run_bootstrap_graph
from app.api.dependencies import DbSession
from app.core.logger import get_logger
from app.core.redis_client import check_redis_connection_sync
from app.retrieval.qdrant_store import (
    ensure_meeting_chunks_collection,
    search_debug_point,
    upsert_debug_point,
)
from app.schemas.reminder import ReminderScanResponse
from app.services.reminders import scan_due_action_item_reminders
from app.workers.celery_app import celery_app
from app.workers.tasks import debug_ping_task

logger = get_logger(__name__)
router = APIRouter(tags=["debug"])


class GraphRunRequest(BaseModel):
    """调试 LangGraph 时使用的请求体。"""

    meeting_id: str


@router.post("/debug/celery-ping")
def create_celery_ping_task():
    """投递一个 Celery 测试任务。"""
    try:
        check_redis_connection_sync()
        task = debug_ping_task.delay()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Celery publish failed: {exc}") from exc
    return {"task_id": task.id, "status": task.status}


@router.get("/debug/celery-tasks/{task_id}")
def get_celery_task_result(task_id: str):
    """查询 Celery 任务状态和结果。"""
    result = celery_app.AsyncResult(task_id)
    response = {"task_id": task_id, "status": result.status}

    if result.successful():
        response["result"] = result.result
    elif result.failed():
        response["error"] = str(result.result)

    return response


@router.post("/debug/qdrant-collection")
def create_qdrant_collection():
    """创建或确认 Qdrant 的 meeting_chunks collection。"""
    try:
        return ensure_meeting_chunks_collection()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Qdrant collection failed: {exc}") from exc


@router.post("/debug/qdrant-upsert")
def create_qdrant_debug_point():
    """写入一条固定测试向量。"""
    try:
        return upsert_debug_point()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Qdrant upsert failed: {exc}") from exc


@router.get("/debug/qdrant-search")
def search_qdrant_debug_point():
    """搜索固定测试向量，验证 Qdrant 检索链路。"""
    try:
        return search_debug_point()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Qdrant search failed: {exc}") from exc


@router.post("/debug/reminders/scan", response_model=ReminderScanResponse)
async def scan_reminders_now(db: DbSession):
    """立即执行一次提醒扫描，方便不启动 Celery Beat 时调试。"""
    result = await scan_due_action_item_reminders(db)
    await db.commit()
    logger.info(
        "调试提醒扫描完成 created_count=%s skipped_count=%s",
        result.created_count,
        result.skipped_count,
    )
    return ReminderScanResponse(
        created_count=result.created_count,
        skipped_count=result.skipped_count,
    )


@router.post("/debug/graph-run")
def run_debug_graph(request: GraphRunRequest):
    """运行最小 LangGraph 流程。"""
    try:
        return run_bootstrap_graph(request.meeting_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"LangGraph run failed: {exc}") from exc
