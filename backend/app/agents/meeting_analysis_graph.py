import asyncio
from datetime import datetime
from functools import lru_cache
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.config import config
from app.core.logger import get_logger
from app.db.session import async_session_factory
from app.llm.dashscope import (
    MEETING_ANALYSIS_PROMPT_VERSION,
    extract_meeting_draft_json,
)
from app.models.analysis import AnalysisDraft
from app.models.meeting import Meeting
from app.models.workflow import WorkflowRun
from app.schemas.analysis import MeetingDraftExtraction
from app.services.analysis_drafts import replace_current_analysis_draft
from app.services.meeting_indexing import index_meeting_documents

logger = get_logger(__name__)


class MeetingAnalysisState(TypedDict):
    """真实会议分析图在节点之间传递的状态。"""

    meeting_id: str
    workflow_run_id: str
    raw_content: str
    occurred_at: datetime | None
    raw_result_json: dict[str, Any]
    extraction: MeetingDraftExtraction | None
    draft_id: str | None
    index_status: str
    index_error_message: str | None
    indexed_chunk_count: int
    current_step: str
    status: str
    error_message: str | None


async def load_meeting(state: MeetingAnalysisState) -> dict[str, Any]:
    """从 MySQL 取出原始会议内容，为 LLM 准备输入。"""
    await _update_workflow(state["workflow_run_id"], current_node="load_meeting", status="running")
    logger.info(
        "会议分析加载会议开始 meeting_id=%s workflow_run_id=%s",
        state["meeting_id"],
        state["workflow_run_id"],
    )
    async with async_session_factory() as db:
        meeting = await db.get(Meeting, state["meeting_id"])
        if meeting is None:
            raise ValueError("meeting not found")
        if not (meeting.raw_content or "").strip():
            raise ValueError("meeting raw content is empty")
        logger.info(
            "会议分析加载会议完成 meeting_id=%s content_chars=%s",
            meeting.id,
            len(meeting.raw_content or ""),
        )
        return {
            "raw_content": meeting.raw_content,
            "occurred_at": meeting.occurred_at,
            "current_step": "load_meeting",
            "status": "running",
        }


async def extract_draft(state: MeetingAnalysisState) -> dict[str, Any]:
    """调用百炼生成 JSON 草稿。"""
    await _update_workflow(state["workflow_run_id"], current_node="extract_draft", status="running")
    logger.info(
        "会议分析调用百炼开始 meeting_id=%s workflow_run_id=%s model=%s",
        state["meeting_id"],
        state["workflow_run_id"],
        config.llm_model,
    )
    raw_result = await asyncio.to_thread(
        extract_meeting_draft_json,
        raw_content=state["raw_content"],
        occurred_at=state["occurred_at"],
    )
    logger.info(
        "会议分析调用百炼完成 meeting_id=%s result_keys=%s",
        state["meeting_id"],
        sorted(raw_result.keys()),
    )
    return {
        "raw_result_json": raw_result,
        "current_step": "extract_draft",
    }


async def validate_draft(state: MeetingAnalysisState) -> dict[str, Any]:
    """Pydantic 是后端最后一道结构校验，不完全相信模型输出。"""
    await _update_workflow(state["workflow_run_id"], current_node="validate_draft", status="running")
    extraction = MeetingDraftExtraction.model_validate(state["raw_result_json"])
    logger.info(
        "会议分析结构校验通过 meeting_id=%s decisions=%s action_items=%s risks=%s unconfirmed=%s",
        state["meeting_id"],
        len(extraction.decisions),
        len(extraction.action_items),
        len(extraction.risk_items),
        len(extraction.unconfirmed_items),
    )
    return {
        "extraction": extraction,
        "current_step": "validate_draft",
    }


async def persist_draft(state: MeetingAnalysisState) -> dict[str, Any]:
    """把通过校验的草稿结果放进 MySQL。"""
    await _update_workflow(state["workflow_run_id"], current_node="persist_draft", status="running")
    logger.info("会议分析草稿落库开始 meeting_id=%s", state["meeting_id"])
    extraction = state["extraction"]
    if extraction is None:
        raise ValueError("meeting draft extraction is missing")

    async with async_session_factory() as db:
        meeting = await db.get(Meeting, state["meeting_id"])
        if meeting is None:
            raise ValueError("meeting not found")
        draft = await replace_current_analysis_draft(
            db=db,
            meeting=meeting,
            extraction=extraction,
            raw_result_json=state["raw_result_json"],
            model_name=config.llm_model,
            prompt_version=MEETING_ANALYSIS_PROMPT_VERSION,
        )
        draft_id = draft.id
        await db.commit()

    logger.info(
        "会议分析草稿落库完成 meeting_id=%s draft_id=%s",
        state["meeting_id"],
        draft_id,
    )
    return {
        "draft_id": draft_id,
        "current_step": "persist_draft",
    }


async def finish(state: MeetingAnalysisState) -> dict[str, Any]:
    """标记这次后台分析流程完成。"""
    await _update_workflow(
        state["workflow_run_id"],
        current_node="finish",
        status="completed",
        error_message=state["index_error_message"],
        payload_updates={
            "index_status": state["index_status"],
            "indexed_chunk_count": state["indexed_chunk_count"],
        },
    )
    logger.info(
        "会议分析流程完成 meeting_id=%s workflow_run_id=%s draft_id=%s index_status=%s indexed_chunk_count=%s",
        state["meeting_id"],
        state["workflow_run_id"],
        state["draft_id"],
        state["index_status"],
        state["indexed_chunk_count"],
    )
    return {
        "status": "draft",
        "current_step": "finish",
        "error_message": None,
    }


async def index_semantic_documents(state: MeetingAnalysisState) -> dict[str, Any]:
    """把当前原文 chunk、决策和待办写入语义索引。"""
    await _update_workflow(
        state["workflow_run_id"],
        current_node="index_semantic_documents",
        status="running",
    )
    draft_id = state["draft_id"]
    if draft_id is None:
        raise ValueError("analysis draft id is missing")
    logger.info(
        "会议语义索引开始 meeting_id=%s draft_id=%s workflow_run_id=%s",
        state["meeting_id"],
        draft_id,
        state["workflow_run_id"],
    )

    async with async_session_factory() as db:
        meeting = await db.get(Meeting, state["meeting_id"])
        if meeting is None:
            raise ValueError("meeting not found")
        statement = (
            select(AnalysisDraft)
            .options(
                selectinload(AnalysisDraft.decisions),
                selectinload(AnalysisDraft.action_items),
            )
            .where(AnalysisDraft.id == draft_id)
        )
        draft = (await db.execute(statement)).scalar_one_or_none()
        if draft is None:
            raise ValueError("analysis draft not found")

        result = await index_meeting_documents(db=db, meeting=meeting, draft=draft)
        await db.commit()

    if result.status == "indexed":
        logger.info(
            "会议语义索引完成 meeting_id=%s draft_id=%s chunk_count=%s",
            state["meeting_id"],
            draft_id,
            result.chunk_count,
        )
    else:
        logger.warning(
            "会议语义索引失败但草稿保留 meeting_id=%s draft_id=%s chunk_count=%s error=%s",
            state["meeting_id"],
            draft_id,
            result.chunk_count,
            result.error_message,
        )
    return {
        "index_status": result.status,
        "index_error_message": result.error_message,
        "indexed_chunk_count": result.chunk_count,
        "current_step": "index_semantic_documents",
    }


@lru_cache
def build_meeting_analysis_graph():
    """LangGraph 只负责分析草稿链路，后续人审再接 checkpoint。"""
    graph = StateGraph(MeetingAnalysisState)
    graph.add_node("load_meeting", load_meeting)
    graph.add_node("extract_draft", extract_draft)
    graph.add_node("validate_draft", validate_draft)
    graph.add_node("persist_draft", persist_draft)
    graph.add_node("index_semantic_documents", index_semantic_documents)
    graph.add_node("finish", finish)

    graph.set_entry_point("load_meeting")
    graph.add_edge("load_meeting", "extract_draft")
    graph.add_edge("extract_draft", "validate_draft")
    graph.add_edge("validate_draft", "persist_draft")
    graph.add_edge("persist_draft", "index_semantic_documents")
    graph.add_edge("index_semantic_documents", "finish")
    graph.add_edge("finish", END)
    return graph.compile()


async def run_meeting_analysis_graph(
    *,
    meeting_id: str,
    workflow_run_id: str,
) -> MeetingAnalysisState:
    initial_state: MeetingAnalysisState = {
        "meeting_id": meeting_id,
        "workflow_run_id": workflow_run_id,
        "raw_content": "",
        "occurred_at": None,
        "raw_result_json": {},
        "extraction": None,
        "draft_id": None,
        "index_status": "pending",
        "index_error_message": None,
        "indexed_chunk_count": 0,
        "current_step": "start",
        "status": "pending",
        "error_message": None,
    }
    try:
        logger.info(
            "会议分析流程启动 meeting_id=%s workflow_run_id=%s",
            meeting_id,
            workflow_run_id,
        )
        return await build_meeting_analysis_graph().ainvoke(initial_state)
    except Exception as exc:
        logger.exception(
            "会议分析流程异常 meeting_id=%s workflow_run_id=%s error=%s",
            meeting_id,
            workflow_run_id,
            exc,
        )
        await _record_analysis_failure(
            meeting_id=meeting_id,
            workflow_run_id=workflow_run_id,
            error_message=str(exc),
        )
        raise


async def _update_workflow(
    workflow_run_id: str,
    *,
    current_node: str,
    status: str,
    error_message: str | None = None,
    payload_updates: dict[str, Any] | None = None,
) -> None:
    async with async_session_factory() as db:
        workflow = await db.get(WorkflowRun, workflow_run_id)
        if workflow is None:
            raise ValueError("workflow run not found")
        workflow.current_node = current_node
        workflow.status = status
        workflow.error_message = error_message
        if payload_updates:
            workflow.payload_json = {**(workflow.payload_json or {}), **payload_updates}
        await db.commit()
    logger.info(
        "工作流状态更新 workflow_run_id=%s current_node=%s status=%s",
        workflow_run_id,
        current_node,
        status,
    )


async def _record_analysis_failure(
    *,
    meeting_id: str,
    workflow_run_id: str,
    error_message: str,
) -> None:
    """失败时保留已有草稿，并把错误记到工作流记录。"""
    async with async_session_factory() as db:
        meeting = await db.get(Meeting, meeting_id)
        workflow = await db.get(WorkflowRun, workflow_run_id)
        if workflow is not None:
            workflow.status = "failed"
            workflow.error_message = error_message

        if meeting is not None:
            statement = (
                select(AnalysisDraft.id)
                .where(AnalysisDraft.meeting_id == meeting.id, AnalysisDraft.status == "draft")
                .limit(1)
            )
            meeting.status = "draft" if await db.scalar(statement) is not None else "failed"
        await db.commit()
    logger.error(
        "会议分析失败已记录 meeting_id=%s workflow_run_id=%s error=%s",
        meeting_id,
        workflow_run_id,
        error_message,
    )
