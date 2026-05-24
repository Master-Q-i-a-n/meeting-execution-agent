from datetime import datetime

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import DbSession, MeetingOccurredAt, MeetingUploadFile, MeetingUploadTitle
from app.core.logger import get_logger
from app.core.redis_client import check_redis_connection_sync
from app.models.analysis import ActionItem, AnalysisDraft
from app.models.meeting import Meeting
from app.models.workflow import WorkflowRun
from app.schemas.analysis import AnalysisDraftResponse, MeetingAnalyzeResponse
from app.schemas.meeting import (
    MeetingCreateTextRequest,
    MeetingDetailResponse,
    MeetingSummaryResponse,
)
from app.services.meeting_content import (
    MAX_MEETING_UPLOAD_BYTES,
    EmptyMeetingContent,
    MeetingContentError,
    UnsupportedMeetingFileType,
    build_paste_metadata,
    normalize_pasted_content,
    parse_uploaded_meeting_file,
)
from app.workers.tasks import analyze_meeting_task

logger = get_logger(__name__)
router = APIRouter(tags=["meetings"])


async def _save_uploaded_meeting(
    *,
    db: AsyncSession,
    title: str | None,
    source_type: str,
    raw_content: str,
    metadata_json: dict,
    occurred_at: datetime | None = None,
) -> Meeting:
    """把已经解析好的会议内容保存到 MySQL。"""
    meeting = Meeting(
        title=title,
        source_type=source_type,
        raw_content=raw_content,
        metadata_json=metadata_json,
        occurred_at=occurred_at,
    )
    db.add(meeting)
    await db.commit()
    await db.refresh(meeting)
    logger.info(
        "会议保存成功 meeting_id=%s source_type=%s content_chars=%s",
        meeting.id,
        source_type,
        len(raw_content),
    )
    return meeting


async def _load_current_analysis_draft(
    db: AsyncSession,
    meeting_id: str,
) -> AnalysisDraft | None:
    """预加载当前执行草稿明细，避免响应序列化时触发懒加载。"""
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
        .where(AnalysisDraft.meeting_id == meeting_id)
        .order_by(AnalysisDraft.created_at.desc())
    )
    result = await db.execute(statement)
    return result.scalars().first()


@router.post("/meetings", response_model=MeetingSummaryResponse)
async def create_meeting_from_text(
    request: MeetingCreateTextRequest,
    db: DbSession,
):
    """粘贴文本/Markdown 创建会议。"""
    try:
        content = normalize_pasted_content(request.content)
    except EmptyMeetingContent as exc:
        logger.warning("粘贴会议创建失败：内容为空")
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    meeting = await _save_uploaded_meeting(
        db=db,
        title=request.title,
        source_type=request.source_type,
        raw_content=content,
        metadata_json=build_paste_metadata(content),
        occurred_at=request.occurred_at,
    )
    logger.info("粘贴会议创建完成 meeting_id=%s", meeting.id)
    return MeetingSummaryResponse.from_model(meeting)


@router.post("/meetings/upload", response_model=MeetingSummaryResponse)
async def upload_meeting_file(
    file: MeetingUploadFile,
    db: DbSession,
    title: MeetingUploadTitle = None,
    occurred_at: MeetingOccurredAt = None,
):
    """上传 txt/Markdown/PDF/Word 会议纪要并保存。"""
    content = await file.read()
    if len(content) > MAX_MEETING_UPLOAD_BYTES:
        logger.warning(
            "会议文件上传失败：文件过大 filename=%s size=%s",
            file.filename,
            len(content),
        )
        raise HTTPException(status_code=413, detail="uploaded file is too large")

    try:
        parsed = parse_uploaded_meeting_file(
            filename=file.filename or "",
            content=content,
            content_type=file.content_type,
        )
    except UnsupportedMeetingFileType as exc:
        logger.warning("会议文件上传失败：类型不支持 filename=%s", file.filename)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MeetingContentError as exc:
        logger.warning("会议文件上传失败：解析错误 filename=%s error=%s", file.filename, exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    meeting = await _save_uploaded_meeting(
        db=db,
        title=title,
        source_type=parsed.source_type,
        raw_content=parsed.text,
        metadata_json=parsed.metadata,
        occurred_at=occurred_at,
    )
    logger.info("会议文件上传完成 meeting_id=%s filename=%s", meeting.id, file.filename)
    return MeetingSummaryResponse.from_model(meeting)


@router.get("/meetings", response_model=list[MeetingSummaryResponse])
async def list_meetings(
    db: DbSession,
    status: str | None = None,
):
    """桌面端会议列表，默认按最近更新时间倒序返回。"""
    statement = select(Meeting)
    if status:
        statement = statement.where(Meeting.status == status)
    statement = statement.order_by(Meeting.updated_at.desc(), Meeting.created_at.desc())
    meetings = (await db.execute(statement)).scalars().all()
    return [MeetingSummaryResponse.from_model(meeting) for meeting in meetings]


@router.get("/meetings/{meeting_id}", response_model=MeetingDetailResponse)
async def get_meeting(
    meeting_id: str,
    db: DbSession,
):
    """按 ID 查看会议原文和当前分析草稿。"""
    result = await db.execute(select(Meeting).where(Meeting.id == meeting_id))
    meeting = result.scalar_one_or_none()
    if meeting is None:
        raise HTTPException(status_code=404, detail="meeting not found")
    draft = await _load_current_analysis_draft(db, meeting.id)
    draft_response = AnalysisDraftResponse.from_model(draft) if draft is not None else None
    return MeetingDetailResponse.from_model(meeting, draft_response)


@router.post("/meetings/{meeting_id}/analyze", response_model=MeetingAnalyzeResponse)
async def analyze_meeting(
    meeting_id: str,
    db: DbSession,
):
    """显式投递会议解析任务，FastAPI 不在请求里等待 LLM。"""
    result = await db.execute(select(Meeting).where(Meeting.id == meeting_id))
    meeting = result.scalar_one_or_none()
    if meeting is None:
        raise HTTPException(status_code=404, detail="meeting not found")
    if not (meeting.raw_content or "").strip():
        raise HTTPException(status_code=400, detail="meeting raw content is empty")

    previous_status = meeting.status
    workflow_run = WorkflowRun(
        meeting_id=meeting.id,
        workflow_type="meeting_analysis",
        current_node="queue",
        status="pending",
        payload_json={"trigger": "api"},
    )
    meeting.status = "analyzing"
    db.add(workflow_run)
    await db.commit()
    await db.refresh(workflow_run)
    logger.info(
        "会议分析任务准备投递 meeting_id=%s workflow_run_id=%s previous_status=%s",
        meeting.id,
        workflow_run.id,
        previous_status,
    )

    try:
        check_redis_connection_sync()
        task = analyze_meeting_task.delay(meeting.id, workflow_run.id)
    except Exception as exc:
        meeting.status = previous_status
        workflow_run.status = "failed"
        workflow_run.current_node = "queue"
        workflow_run.error_message = f"Celery publish failed: {exc}"
        await db.commit()
        logger.exception(
            "会议分析任务投递失败 meeting_id=%s workflow_run_id=%s error=%s",
            meeting.id,
            workflow_run.id,
            exc,
        )
        raise HTTPException(status_code=503, detail=f"Celery publish failed: {exc}") from exc

    logger.info(
        "会议分析任务投递成功 meeting_id=%s workflow_run_id=%s task_id=%s",
        meeting.id,
        workflow_run.id,
        task.id,
    )
    return MeetingAnalyzeResponse(
        meeting_id=meeting.id,
        workflow_run_id=workflow_run.id,
        task_id=task.id,
        status=task.status,
    )
