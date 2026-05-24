import asyncio
from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import get_logger
from app.llm.dashscope import embed_texts, generate_meeting_question_answer
from app.models.analysis import ActionItem, AnalysisDraft, Decision
from app.models.meeting import Meeting
from app.retrieval.qdrant_store import SemanticSearchPoint, search_meeting_chunks

logger = get_logger(__name__)

NO_EVIDENCE_ANSWER = "没有找到足够的会议依据回答这个问题。"


async def answer_meeting_question(
    *,
    db: AsyncSession,
    question: str,
    top_k: int,
    meeting_id: str | None = None,
    embedder: Callable[[list[str]], list[list[float]]] = embed_texts,
    searcher: Callable[..., list[SemanticSearchPoint]] = search_meeting_chunks,
    answer_generator: Callable[..., str] = generate_meeting_question_answer,
) -> dict[str, Any]:
    """执行 MySQL + Qdrant 双路追问。

    Qdrant 负责先召回语义片段，MySQL 再补结构化事实，最终交给 LLM 生成带引用回答。
    """
    logger.info(
        "会议追问开始 meeting_id=%s top_k=%s question_chars=%s",
        meeting_id or "all",
        top_k,
        len(question),
    )
    vectors = await asyncio.to_thread(embedder, [question])
    query_vector = vectors[0]
    logger.info("会议追问向量化完成 meeting_id=%s", meeting_id or "all")
    search_results = await asyncio.to_thread(
        searcher,
        query_vector=query_vector,
        limit=top_k,
        meeting_id=meeting_id,
    )
    logger.info(
        "会议追问 Qdrant 召回完成 meeting_id=%s result_count=%s",
        meeting_id or "all",
        len(search_results),
    )
    citations = build_citations(search_results)
    structured_facts = await load_structured_facts(db, citations)

    if not citations:
        logger.warning(
            "会议追问没有召回依据 meeting_id=%s top_k=%s",
            meeting_id or "all",
            top_k,
        )
        return {
            "answer": NO_EVIDENCE_ANSWER,
            "citations": [],
            "structured_facts": structured_facts,
        }

    answer = await asyncio.to_thread(
        answer_generator,
        question=question,
        citations=citations,
        structured_facts=structured_facts,
    )
    logger.info(
        "会议追问回答生成完成 meeting_id=%s citation_count=%s",
        meeting_id or "all",
        len(citations),
    )
    return {
        "answer": answer,
        "citations": citations,
        "structured_facts": structured_facts,
    }


def build_citations(search_results: list[SemanticSearchPoint]) -> list[dict[str, Any]]:
    """把 Qdrant payload 整理成 API 可返回的引用格式。"""
    citations: list[dict[str, Any]] = []
    for result in search_results:
        payload = result.payload
        citations.append(
            {
                "meeting_id": payload.get("meeting_id"),
                "chunk_id": payload.get("chunk_id") or result.point_id,
                "chunk_type": payload.get("chunk_type"),
                "source_id": payload.get("source_id"),
                "text": payload.get("text"),
                "source_excerpt": payload.get("source_excerpt"),
                "score": result.score,
            }
        )
    return citations


async def load_structured_facts(
    db: AsyncSession,
    citations: list[dict[str, Any]],
) -> dict[str, Any]:
    """根据 citation 里的业务 ID 回 MySQL 查结构化事实。"""
    meeting_ids = {
        citation["meeting_id"]
        for citation in citations
        if citation.get("meeting_id")
    }
    decision_ids = {
        citation["source_id"]
        for citation in citations
        if citation.get("chunk_type") == "decision" and citation.get("source_id")
    }
    action_item_ids = {
        citation["source_id"]
        for citation in citations
        if citation.get("chunk_type") == "action_item" and citation.get("source_id")
    }

    decisions = await _load_decision_facts(db, decision_ids)
    action_items = await _load_action_item_facts(db, action_item_ids)
    meetings = await _load_meeting_facts(db, meeting_ids)
    return {
        "meetings": meetings,
        "decisions": decisions,
        "action_items": action_items,
    }


async def _load_meeting_facts(db: AsyncSession, meeting_ids: set[str]) -> list[dict[str, Any]]:
    if not meeting_ids:
        return []
    rows = (
        await db.execute(select(Meeting).where(Meeting.id.in_(meeting_ids)))
    ).scalars().all()
    return [
        {
            "id": meeting.id,
            "title": meeting.title,
            "source_type": meeting.source_type,
            "status": meeting.status,
            "occurred_at": meeting.occurred_at.isoformat() if meeting.occurred_at else None,
        }
        for meeting in rows
    ]


async def _load_decision_facts(db: AsyncSession, decision_ids: set[str]) -> list[dict[str, Any]]:
    if not decision_ids:
        return []
    statement = (
        select(Decision, AnalysisDraft.meeting_id)
        .join(AnalysisDraft, Decision.analysis_draft_id == AnalysisDraft.id)
        .where(Decision.id.in_(decision_ids))
    )
    rows = (await db.execute(statement)).all()
    return [
        {
            "id": decision.id,
            "meeting_id": meeting_id,
            "summary": decision.summary,
            "status": decision.status,
            "source_excerpt": decision.source_excerpt,
            "confidence": decision.confidence,
        }
        for decision, meeting_id in rows
    ]


async def _load_action_item_facts(
    db: AsyncSession,
    action_item_ids: set[str],
) -> list[dict[str, Any]]:
    if not action_item_ids:
        return []
    statement = (
        select(ActionItem, AnalysisDraft.meeting_id)
        .join(AnalysisDraft, ActionItem.analysis_draft_id == AnalysisDraft.id)
        .where(ActionItem.id.in_(action_item_ids))
    )
    rows = (await db.execute(statement)).all()
    return [
        {
            "id": item.id,
            "meeting_id": meeting_id,
            "title": item.title,
            "description": item.description,
            "owner_name": item.owner_name,
            "deadline_text": item.deadline_text,
            "due_at": item.due_at.isoformat() if item.due_at else None,
            "priority": item.priority,
            "status": item.status,
            "source_excerpt": item.source_excerpt,
            "confidence": item.confidence,
        }
        for item, meeting_id in rows
    ]
