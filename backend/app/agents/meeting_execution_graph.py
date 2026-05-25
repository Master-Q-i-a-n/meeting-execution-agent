import asyncio
from datetime import datetime
from functools import lru_cache
from typing import Any, Literal, TypedDict

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
from app.models.analysis import ActionItem, AnalysisDraft
from app.models.meeting import Meeting
from app.models.workflow import WorkflowRun
from app.schemas.analysis import MeetingDraftExtraction
from app.services.analysis_drafts import replace_current_analysis_draft
from app.services.clarification_rules import normalize_meeting_clarifications
from app.services.execution_drafts import confirm_execution_draft
from app.services.meeting_indexing import index_meeting_documents
from app.services.task_dispatch import run_external_task_dispatch

logger = get_logger(__name__)

ResumeAction = Literal[
    "start",
    "retry_input",
    "retry_extraction",
    "force_continue",
    "confirm_draft",
    "retry_dispatch",
]

WAITING_INPUT_CLARIFICATION = "waiting_input_clarification"
WAITING_CLARIFICATION = "waiting_clarification"
WAITING_CONFIRMATION = "waiting_confirmation"


class MeetingExecutionState(TypedDict):
    """会议执行图在节点之间传递的状态。

    LangGraph 仍然只保存本次运行的内存 state；可恢复的事实放在 workflow_runs
    和 MySQL 业务表里，所以 Celery 重启后仍能通过 resume_action 继续流程。
    """

    meeting_id: str
    workflow_run_id: str
    resume_action: str
    raw_content: str
    occurred_at: datetime | None
    raw_result_json: dict[str, Any]
    extraction: MeetingDraftExtraction | None
    draft_id: str | None
    input_quality_status: str
    input_quality_reason: str | None
    unconfirmed_count: int
    index_status: str
    index_error_message: str | None
    indexed_chunk_count: int
    dispatch_status: str | None
    dispatch_error_message: str | None
    dispatch_succeeded_count: int
    dispatch_skipped_count: int
    dispatch_failed_count: int
    snapshot_id: str | None
    current_step: str
    status: str
    error_message: str | None


async def route_resume(state: MeetingExecutionState) -> dict[str, Any]:
    """根据 resume_action 选择从哪个节点继续。

    首次 analyze 从 load_meeting 开始；人工确认、强制继续和重派则直接从对应
    的后半段节点恢复，这就是当前版本的“长流程恢复”边界。
    """
    await _update_workflow(
        state["workflow_run_id"],
        current_node="route_resume",
        status="running",
        payload_updates={"resume_action": state["resume_action"]},
    )
    return {"current_step": "route_resume", "status": "running"}


async def load_meeting(state: MeetingExecutionState) -> dict[str, Any]:
    """从 MySQL 读取会议原文，为后续规则检查和 LLM 抽取准备输入。"""
    await _update_workflow(
        state["workflow_run_id"],
        current_node="load_meeting",
        status="running",
    )
    logger.info(
        "会议工作流加载会议开始 meeting_id=%s workflow_run_id=%s",
        state["meeting_id"],
        state["workflow_run_id"],
    )
    async with async_session_factory() as db:
        meeting = await db.get(Meeting, state["meeting_id"])
        if meeting is None:
            raise ValueError("meeting not found")
        logger.info(
            "会议工作流加载会议完成 meeting_id=%s content_chars=%s",
            meeting.id,
            len(meeting.raw_content or ""),
        )
        return {
            "raw_content": meeting.raw_content or "",
            "occurred_at": meeting.occurred_at,
            "current_step": "load_meeting",
            "status": "running",
        }


async def check_input_quality(state: MeetingExecutionState) -> dict[str, Any]:
    """先用稳定规则判断输入是否值得进入 LLM。

    这一版不为质量判断额外调用模型：明显空、过短、疑似乱码的内容直接等待
    用户补充，避免浪费 LLM 调用并让 Trace 能解释为什么暂停。
    """
    await _update_workflow(
        state["workflow_run_id"],
        current_node="check_input_quality",
        status="running",
    )
    quality_status, reason = inspect_meeting_input_quality(state["raw_content"])
    logger.info(
        "会议输入质量检查完成 meeting_id=%s status=%s reason=%s",
        state["meeting_id"],
        quality_status,
        reason,
    )
    return {
        "input_quality_status": quality_status,
        "input_quality_reason": reason,
        "current_step": "check_input_quality",
    }


async def wait_for_input_clarification(state: MeetingExecutionState) -> dict[str, Any]:
    """输入质量不够时暂停工作流，等待用户修正会议原文后再继续。"""
    await _update_workflow(
        state["workflow_run_id"],
        current_node="wait_for_input_clarification",
        status=WAITING_INPUT_CLARIFICATION,
        payload_updates={
            "input_quality_status": state["input_quality_status"],
            "input_quality_reason": state["input_quality_reason"],
        },
        meeting_status="needs_input",
    )
    logger.info(
        "会议工作流等待补充输入 meeting_id=%s workflow_run_id=%s reason=%s",
        state["meeting_id"],
        state["workflow_run_id"],
        state["input_quality_reason"],
    )
    return {
        "current_step": "wait_for_input_clarification",
        "status": WAITING_INPUT_CLARIFICATION,
        "error_message": state["input_quality_reason"],
    }


async def extract_draft(state: MeetingExecutionState) -> dict[str, Any]:
    """调用百炼生成结构化 JSON 草稿。"""
    await _update_workflow(
        state["workflow_run_id"],
        current_node="extract_draft",
        status="running",
    )
    logger.info(
        "会议工作流调用百炼开始 meeting_id=%s workflow_run_id=%s model=%s",
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
        "会议工作流调用百炼完成 meeting_id=%s result_keys=%s",
        state["meeting_id"],
        sorted(raw_result.keys()),
    )
    return {
        "raw_result_json": raw_result,
        "current_step": "extract_draft",
    }


async def validate_draft(state: MeetingExecutionState) -> dict[str, Any]:
    """用 Pydantic 校验模型输出，避免半成品草稿落库。"""
    await _update_workflow(
        state["workflow_run_id"],
        current_node="validate_draft",
        status="running",
    )
    extraction = MeetingDraftExtraction.model_validate(state["raw_result_json"])
    logger.info(
        "会议工作流结构校验通过 meeting_id=%s decisions=%s action_items=%s risks=%s unconfirmed=%s",
        state["meeting_id"],
        len(extraction.decisions),
        len(extraction.action_items),
        len(extraction.risk_items),
        len(extraction.unconfirmed_items),
    )
    return {
        "extraction": extraction,
        "unconfirmed_count": len(extraction.unconfirmed_items),
        "current_step": "validate_draft",
    }


async def normalize_clarifications(state: MeetingExecutionState) -> dict[str, Any]:
    """用确定性规则补齐负责人和截止时间缺失产生的待澄清项。"""
    await _update_workflow(
        state["workflow_run_id"],
        current_node="normalize_clarifications",
        status="running",
    )
    extraction = state["extraction"]
    if extraction is None:
        raise ValueError("meeting draft extraction is missing")
    normalized_extraction = normalize_meeting_clarifications(extraction)
    logger.info(
        "会议工作流澄清项归一完成 meeting_id=%s unconfirmed=%s",
        state["meeting_id"],
        len(normalized_extraction.unconfirmed_items),
    )
    return {
        "extraction": normalized_extraction,
        "unconfirmed_count": len(normalized_extraction.unconfirmed_items),
        "current_step": "normalize_clarifications",
    }


async def persist_draft(state: MeetingExecutionState) -> dict[str, Any]:
    """把通过校验的草稿写入 MySQL。"""
    await _update_workflow(
        state["workflow_run_id"],
        current_node="persist_draft",
        status="running",
    )
    logger.info("会议工作流草稿落库开始 meeting_id=%s", state["meeting_id"])
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

    await _update_workflow(
        state["workflow_run_id"],
        current_node="persist_draft",
        status="running",
        payload_updates={
            "draft_id": draft_id,
            "unconfirmed_count": state["unconfirmed_count"],
        },
    )
    logger.info(
        "会议工作流草稿落库完成 meeting_id=%s draft_id=%s",
        state["meeting_id"],
        draft_id,
    )
    return {
        "draft_id": draft_id,
        "current_step": "persist_draft",
    }


async def route_unconfirmed_items(state: MeetingExecutionState) -> dict[str, Any]:
    """记录未确认项数量，并由条件边决定是否暂停等待澄清。"""
    await _update_workflow(
        state["workflow_run_id"],
        current_node="route_unconfirmed_items",
        status="running",
        payload_updates={
            "draft_id": state["draft_id"],
            "unconfirmed_count": state["unconfirmed_count"],
        },
    )
    return {"current_step": "route_unconfirmed_items"}


async def wait_for_clarification(state: MeetingExecutionState) -> dict[str, Any]:
    """有未确认项时暂停，但允许用户强制继续。"""
    await _update_workflow(
        state["workflow_run_id"],
        current_node="wait_for_clarification",
        status=WAITING_CLARIFICATION,
        payload_updates={
            "draft_id": state["draft_id"],
            "unconfirmed_count": state["unconfirmed_count"],
            "can_force_continue": True,
        },
        meeting_status="draft",
    )
    logger.info(
        "会议工作流等待澄清 meeting_id=%s workflow_run_id=%s draft_id=%s unconfirmed_count=%s",
        state["meeting_id"],
        state["workflow_run_id"],
        state["draft_id"],
        state["unconfirmed_count"],
    )
    return {
        "current_step": "wait_for_clarification",
        "status": WAITING_CLARIFICATION,
    }


async def index_semantic_documents(state: MeetingExecutionState) -> dict[str, Any]:
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


async def wait_for_confirmation(state: MeetingExecutionState) -> dict[str, Any]:
    """分析和索引结束后暂停，等待用户编辑并确认草稿。"""
    await _update_workflow(
        state["workflow_run_id"],
        current_node="wait_for_confirmation",
        status=WAITING_CONFIRMATION,
        error_message=state["index_error_message"],
        payload_updates={
            "draft_id": state["draft_id"],
            "index_status": state["index_status"],
            "indexed_chunk_count": state["indexed_chunk_count"],
            "unconfirmed_count": state["unconfirmed_count"],
        },
        meeting_status="draft",
    )
    logger.info(
        "会议工作流等待人工确认 meeting_id=%s workflow_run_id=%s draft_id=%s index_status=%s",
        state["meeting_id"],
        state["workflow_run_id"],
        state["draft_id"],
        state["index_status"],
    )
    return {
        "status": WAITING_CONFIRMATION,
        "current_step": "wait_for_confirmation",
        "error_message": state["index_error_message"],
    }


async def confirm_draft(state: MeetingExecutionState) -> dict[str, Any]:
    """用户确认后生成快照，并把待办推进到 confirmed。"""
    await _update_workflow(
        state["workflow_run_id"],
        current_node="confirm_draft",
        status="running",
    )
    draft_id = state["draft_id"]
    if draft_id is None:
        raise ValueError("analysis draft id is missing")
    async with async_session_factory() as db:
        draft = await _load_draft_detail(db, draft_id)
        if draft is None:
            raise ValueError("analysis draft not found")
        snapshot = confirm_execution_draft(draft)
        db.add(snapshot)
        await db.commit()
        snapshot_id = snapshot.id

    await _update_workflow(
        state["workflow_run_id"],
        current_node="confirm_draft",
        status="running",
        payload_updates={"draft_id": draft_id, "snapshot_id": snapshot_id},
    )
    logger.info(
        "会议工作流草稿确认完成 meeting_id=%s draft_id=%s snapshot_id=%s",
        state["meeting_id"],
        draft_id,
        snapshot_id,
    )
    return {
        "snapshot_id": snapshot_id,
        "current_step": "confirm_draft",
    }


async def retry_dispatch(state: MeetingExecutionState) -> dict[str, Any]:
    """失败后重派前先记录重试次数，后续派发服务会跳过已成功映射。"""
    await _update_workflow(
        state["workflow_run_id"],
        current_node="retry_dispatch",
        status="running",
        increment_retry_count=True,
        payload_updates={"resume_action": "retry_dispatch"},
    )
    logger.info(
        "会议工作流准备重试派发 workflow_run_id=%s draft_id=%s",
        state["workflow_run_id"],
        state["draft_id"],
    )
    return {"current_step": "retry_dispatch"}


async def dispatch_tasks(state: MeetingExecutionState) -> dict[str, Any]:
    """调用外部任务派发服务，创建 Linear Issue 并写入 tool_calls。"""
    await _update_workflow(
        state["workflow_run_id"],
        current_node="dispatch_tasks",
        status="running",
    )
    draft_id = state["draft_id"]
    if draft_id is None:
        raise ValueError("analysis draft id is missing")

    result = await run_external_task_dispatch(
        draft_id=draft_id,
        workflow_run_id=state["workflow_run_id"],
    )
    error_message = None if result.status == "completed" else "one or more action items failed to dispatch"
    logger.info(
        "会议工作流派发完成 draft_id=%s workflow_run_id=%s status=%s succeeded=%s skipped=%s failed=%s",
        result.draft_id,
        result.workflow_run_id,
        result.status,
        result.succeeded_count,
        result.skipped_count,
        result.failed_count,
    )
    return {
        "dispatch_status": result.status,
        "dispatch_error_message": error_message,
        "dispatch_succeeded_count": result.succeeded_count,
        "dispatch_skipped_count": result.skipped_count,
        "dispatch_failed_count": result.failed_count,
        "current_step": "dispatch_tasks",
    }


async def route_dispatch_result(state: MeetingExecutionState) -> dict[str, Any]:
    """把派发统计写入 workflow payload，再根据状态走完成或失败分支。"""
    await _update_workflow(
        state["workflow_run_id"],
        current_node="route_dispatch_result",
        status="running",
        error_message=state["dispatch_error_message"],
        payload_updates=_build_dispatch_payload(state),
    )
    return {"current_step": "route_dispatch_result"}


async def finish_completed(state: MeetingExecutionState) -> dict[str, Any]:
    """全部派发成功后结束同一个会议执行工作流。"""
    await _update_workflow(
        state["workflow_run_id"],
        current_node="finish_completed",
        status="completed",
        error_message=None,
        payload_updates=_build_dispatch_payload(state),
        meeting_status="completed",
    )
    logger.info(
        "会议执行工作流完成 meeting_id=%s workflow_run_id=%s draft_id=%s",
        state["meeting_id"],
        state["workflow_run_id"],
        state["draft_id"],
    )
    return {
        "status": "completed",
        "current_step": "finish_completed",
        "error_message": None,
    }


async def finish_failed(state: MeetingExecutionState) -> dict[str, Any]:
    """不可自动恢复或派发失败时结束到 failed，等待用户修复后手动重试。"""
    error_message = state["dispatch_error_message"] or state["error_message"] or "workflow failed"
    await _update_workflow(
        state["workflow_run_id"],
        current_node="finish_failed",
        status="failed",
        error_message=error_message,
        payload_updates=_build_dispatch_payload(state),
        meeting_status="failed",
    )
    logger.warning(
        "会议执行工作流失败 meeting_id=%s workflow_run_id=%s draft_id=%s error=%s",
        state["meeting_id"],
        state["workflow_run_id"],
        state["draft_id"],
        error_message,
    )
    return {
        "status": "failed",
        "current_step": "finish_failed",
        "error_message": error_message,
    }


@lru_cache
def build_meeting_execution_graph():
    """构建带条件分支和人工等待点的会议执行图。"""
    graph = StateGraph(MeetingExecutionState)
    graph.add_node("route_resume", route_resume)
    graph.add_node("load_meeting", load_meeting)
    graph.add_node("check_input_quality", check_input_quality)
    graph.add_node("wait_for_input_clarification", wait_for_input_clarification)
    graph.add_node("extract_draft", extract_draft)
    graph.add_node("validate_draft", validate_draft)
    graph.add_node("normalize_clarifications", normalize_clarifications)
    graph.add_node("persist_draft", persist_draft)
    graph.add_node("route_unconfirmed_items", route_unconfirmed_items)
    graph.add_node("wait_for_clarification", wait_for_clarification)
    graph.add_node("index_semantic_documents", index_semantic_documents)
    graph.add_node("wait_for_confirmation", wait_for_confirmation)
    graph.add_node("confirm_draft", confirm_draft)
    graph.add_node("retry_dispatch", retry_dispatch)
    graph.add_node("dispatch_tasks", dispatch_tasks)
    graph.add_node("route_dispatch_result", route_dispatch_result)
    graph.add_node("finish_completed", finish_completed)
    graph.add_node("finish_failed", finish_failed)

    graph.set_entry_point("route_resume")
    graph.add_conditional_edges(
        "route_resume",
        _route_from_resume_action,
        {
            "load_meeting": "load_meeting",
            "index_semantic_documents": "index_semantic_documents",
            "confirm_draft": "confirm_draft",
            "retry_dispatch": "retry_dispatch",
        },
    )
    graph.add_edge("load_meeting", "check_input_quality")
    graph.add_conditional_edges(
        "check_input_quality",
        _route_from_input_quality,
        {
            "extract_draft": "extract_draft",
            "wait_for_input_clarification": "wait_for_input_clarification",
        },
    )
    graph.add_edge("wait_for_input_clarification", END)
    graph.add_edge("extract_draft", "validate_draft")
    graph.add_edge("validate_draft", "normalize_clarifications")
    graph.add_edge("normalize_clarifications", "persist_draft")
    graph.add_edge("persist_draft", "route_unconfirmed_items")
    graph.add_conditional_edges(
        "route_unconfirmed_items",
        _route_from_unconfirmed_items,
        {
            "wait_for_clarification": "wait_for_clarification",
            "index_semantic_documents": "index_semantic_documents",
        },
    )
    graph.add_edge("wait_for_clarification", END)
    graph.add_edge("index_semantic_documents", "wait_for_confirmation")
    graph.add_edge("wait_for_confirmation", END)
    graph.add_edge("confirm_draft", "dispatch_tasks")
    graph.add_edge("retry_dispatch", "dispatch_tasks")
    graph.add_edge("dispatch_tasks", "route_dispatch_result")
    graph.add_conditional_edges(
        "route_dispatch_result",
        _route_from_dispatch_result,
        {
            "finish_completed": "finish_completed",
            "finish_failed": "finish_failed",
        },
    )
    graph.add_edge("finish_completed", END)
    graph.add_edge("finish_failed", END)
    return graph.compile()


async def run_meeting_execution_graph(
    *,
    meeting_id: str,
    workflow_run_id: str,
) -> MeetingExecutionState:
    """首次启动会议执行工作流。"""
    initial_state = _build_initial_state(
        meeting_id=meeting_id,
        workflow_run_id=workflow_run_id,
        resume_action="start",
    )
    return await _invoke_graph(initial_state)


async def resume_meeting_execution_workflow(
    *,
    workflow_run_id: str,
    resume_action: ResumeAction,
) -> MeetingExecutionState:
    """从 workflow_runs 记录恢复等待中的会议执行工作流。"""
    initial_state = await _build_resume_state(
        workflow_run_id=workflow_run_id,
        resume_action=resume_action,
    )
    return await _invoke_graph(initial_state)


async def _invoke_graph(initial_state: MeetingExecutionState) -> MeetingExecutionState:
    try:
        logger.info(
            "会议执行工作流启动 meeting_id=%s workflow_run_id=%s resume_action=%s",
            initial_state["meeting_id"],
            initial_state["workflow_run_id"],
            initial_state["resume_action"],
        )
        return await build_meeting_execution_graph().ainvoke(initial_state)
    except Exception as exc:
        logger.exception(
            "会议执行工作流异常 meeting_id=%s workflow_run_id=%s error=%s",
            initial_state["meeting_id"],
            initial_state["workflow_run_id"],
            exc,
        )
        await _record_analysis_failure(
            meeting_id=initial_state["meeting_id"],
            workflow_run_id=initial_state["workflow_run_id"],
            error_message=str(exc),
        )
        raise


async def _build_resume_state(
    *,
    workflow_run_id: str,
    resume_action: ResumeAction,
) -> MeetingExecutionState:
    async with async_session_factory() as db:
        workflow = await db.get(WorkflowRun, workflow_run_id)
        if workflow is None:
            raise ValueError("workflow run not found")
        if workflow.meeting_id is None:
            raise ValueError("workflow run is not attached to a meeting")
        payload = workflow.payload_json or {}
        draft_id = payload.get("draft_id")
        if draft_id is None:
            draft_id = await db.scalar(
                select(AnalysisDraft.id)
                .where(
                    AnalysisDraft.meeting_id == workflow.meeting_id,
                    AnalysisDraft.status.in_(["draft", "confirmed", "dispatching", "failed"]),
                )
                .order_by(AnalysisDraft.created_at.desc())
                .limit(1)
            )

    return _build_initial_state(
        meeting_id=workflow.meeting_id,
        workflow_run_id=workflow_run_id,
        resume_action=resume_action,
        draft_id=draft_id,
        index_status=str(payload.get("index_status") or "pending"),
        indexed_chunk_count=int(payload.get("indexed_chunk_count") or 0),
        unconfirmed_count=int(payload.get("unconfirmed_count") or 0),
    )


def _build_initial_state(
    *,
    meeting_id: str,
    workflow_run_id: str,
    resume_action: ResumeAction,
    draft_id: str | None = None,
    index_status: str = "pending",
    indexed_chunk_count: int = 0,
    unconfirmed_count: int = 0,
) -> MeetingExecutionState:
    return {
        "meeting_id": meeting_id,
        "workflow_run_id": workflow_run_id,
        "resume_action": resume_action,
        "raw_content": "",
        "occurred_at": None,
        "raw_result_json": {},
        "extraction": None,
        "draft_id": draft_id,
        "input_quality_status": "pending",
        "input_quality_reason": None,
        "unconfirmed_count": unconfirmed_count,
        "index_status": index_status,
        "index_error_message": None,
        "indexed_chunk_count": indexed_chunk_count,
        "dispatch_status": None,
        "dispatch_error_message": None,
        "dispatch_succeeded_count": 0,
        "dispatch_skipped_count": 0,
        "dispatch_failed_count": 0,
        "snapshot_id": None,
        "current_step": "start",
        "status": "pending",
        "error_message": None,
    }


def inspect_meeting_input_quality(raw_content: str) -> tuple[str, str | None]:
    """规则化检查会议文本质量，返回 ok 或 needs_clarification。"""
    content = raw_content.strip()
    if not content:
        return "needs_clarification", "meeting raw content is empty"
    if len(content) < 50:
        return "needs_clarification", "meeting raw content is too short"

    replacement_count = content.count("\ufffd")
    control_count = sum(1 for char in content if ord(char) < 32 and char not in "\r\n\t")
    suspicious_ratio = (replacement_count + control_count) / max(len(content), 1)
    if suspicious_ratio > 0.05:
        return "needs_clarification", "meeting raw content looks garbled"

    natural_count = sum(
        1
        for char in content
        if char.isalnum() or "\u4e00" <= char <= "\u9fff"
    )
    if natural_count / max(len(content), 1) < 0.2:
        return "needs_clarification", "meeting raw content lacks readable sentences"

    return "ok", None


def _route_from_resume_action(state: MeetingExecutionState) -> str:
    action = state["resume_action"]
    if action in {"start", "retry_input", "retry_extraction"}:
        return "load_meeting"
    if action == "force_continue":
        return "index_semantic_documents"
    if action == "confirm_draft":
        return "confirm_draft"
    if action == "retry_dispatch":
        return "retry_dispatch"
    raise ValueError(f"unsupported resume action: {action}")


def _route_from_input_quality(state: MeetingExecutionState) -> str:
    if state["input_quality_status"] == "ok":
        return "extract_draft"
    return "wait_for_input_clarification"


def _route_from_unconfirmed_items(state: MeetingExecutionState) -> str:
    if state["unconfirmed_count"] > 0:
        return "wait_for_clarification"
    return "index_semantic_documents"


def _route_from_dispatch_result(state: MeetingExecutionState) -> str:
    if state["dispatch_status"] == "completed":
        return "finish_completed"
    return "finish_failed"


def _build_dispatch_payload(state: MeetingExecutionState) -> dict[str, Any]:
    return {
        "draft_id": state["draft_id"],
        "dispatch_status": state["dispatch_status"],
        "succeeded_count": state["dispatch_succeeded_count"],
        "skipped_count": state["dispatch_skipped_count"],
        "failed_count": state["dispatch_failed_count"],
    }


async def _load_draft_detail(db, draft_id: str) -> AnalysisDraft | None:
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
    return (await db.execute(statement)).scalars().first()


async def _update_workflow(
    workflow_run_id: str,
    *,
    current_node: str,
    status: str,
    error_message: str | None = None,
    payload_updates: dict[str, Any] | None = None,
    meeting_status: str | None = None,
    increment_retry_count: bool = False,
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
        if increment_retry_count:
            workflow.retry_count += 1
        if meeting_status and workflow.meeting_id:
            meeting = await db.get(Meeting, workflow.meeting_id)
            if meeting is not None:
                meeting.status = meeting_status
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
    """失败时保留已有草稿，并把错误记录到 workflow_run。"""
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
        "会议执行工作流失败已记录 meeting_id=%s workflow_run_id=%s error=%s",
        meeting_id,
        workflow_run_id,
        error_message,
    )
