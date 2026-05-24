from fastapi import APIRouter, HTTPException

from app.api.dependencies import DbSession
from app.core.logger import get_logger
from app.models.meeting import Meeting
from app.schemas.qa import MeetingAskRequest, MeetingAskResponse
from app.services.meeting_qa import answer_meeting_question

logger = get_logger(__name__)
router = APIRouter(tags=["qa"])


@router.post("/meetings/{meeting_id}/ask", response_model=MeetingAskResponse)
async def ask_single_meeting(
    meeting_id: str,
    request: MeetingAskRequest,
    db: DbSession,
):
    """针对单场会议追问，只检索该会议写入 Qdrant 的语义片段。"""
    meeting = await db.get(Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="meeting not found")

    try:
        logger.info("单会议追问请求 meeting_id=%s top_k=%s", meeting_id, request.top_k)
        return await answer_meeting_question(
            db=db,
            question=request.question,
            top_k=request.top_k,
            meeting_id=meeting_id,
        )
    except Exception as exc:
        logger.exception("单会议追问失败 meeting_id=%s error=%s", meeting_id, exc)
        raise HTTPException(status_code=503, detail=f"meeting ask failed: {exc}") from exc


@router.post("/ask", response_model=MeetingAskResponse)
async def ask_across_meetings(
    request: MeetingAskRequest,
    db: DbSession,
):
    """跨会议追问，先用 Qdrant 召回相关片段，再回 MySQL 补结构化事实。"""
    try:
        logger.info("跨会议追问请求 top_k=%s", request.top_k)
        return await answer_meeting_question(
            db=db,
            question=request.question,
            top_k=request.top_k,
        )
    except Exception as exc:
        logger.exception("跨会议追问失败 error=%s", exc)
        raise HTTPException(status_code=503, detail=f"meeting ask failed: {exc}") from exc
