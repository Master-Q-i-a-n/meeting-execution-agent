from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from qdrant_client.models import PointStruct

from app.evals.dataset_loader import EvalCase
from app.integrations.linear import LINEAR_PROVIDER
from app.llm.dashscope import (
    embed_texts,
    extract_meeting_draft_json,
    generate_meeting_question_answer,
)
from app.retrieval.qdrant_store import replace_meeting_points, search_meeting_chunks
from app.schemas.analysis import MeetingDraftExtraction
from app.services.clarification_rules import normalize_meeting_clarifications
from app.services.meeting_qa import build_citations
from app.services.task_dispatch import build_dispatch_idempotency_key


def run_extraction_target(inputs: dict[str, Any]) -> dict[str, Any]:
    """Real DashScope extraction target for LangSmith."""
    try:
        raw_result = extract_meeting_draft_json(
            raw_content=inputs["raw_content"],
            occurred_at=_parse_datetime(inputs.get("occurred_at")),
        )
        extraction = MeetingDraftExtraction.model_validate(raw_result)
        normalized = normalize_meeting_clarifications(extraction)
    except Exception as exc:
        return {
            "schema_valid": False,
            "error": str(exc),
            "decision_summary": "",
            "decisions": [],
            "action_items": [],
            "risk_items": [],
            "unconfirmed_items": [],
        }

    return {
        "schema_valid": True,
        **normalized.model_dump(mode="json"),
    }


def run_qa_target(inputs: dict[str, Any]) -> dict[str, Any]:
    """Real embedding + Qdrant + DashScope QA target.

    QA evals seed each local meeting sample into Qdrant with an eval-* meeting_id,
    then perform the same vector retrieval and grounded-answer generation path.
    """
    try:
        meeting_id = inputs.get("eval_meeting_id") or f"eval-{inputs['base_case_id']}"
        _seed_eval_meeting_points(
            meeting_id=meeting_id,
            title=inputs.get("title", ""),
            raw_content=inputs["raw_content"],
        )
        question_vector = embed_texts([inputs["question"]])[0]
        search_results = search_meeting_chunks(
            query_vector=question_vector,
            limit=int(inputs.get("top_k") or 5),
            meeting_id=meeting_id,
        )
        citations = build_citations(search_results)
        structured_facts = {
            "meetings": [
                {
                    "id": meeting_id,
                    "title": inputs.get("title"),
                    "source_type": "langsmith_eval",
                }
            ],
            "decisions": [],
            "action_items": [],
        }
        if not citations:
            return {
                "answer": "没有找到足够的会议依据回答这个问题。",
                "citations": [],
                "structured_facts": structured_facts,
            }
        answer = generate_meeting_question_answer(
            question=inputs["question"],
            citations=citations,
            structured_facts=structured_facts,
        )
        return {
            "answer": answer,
            "citations": citations,
            "structured_facts": structured_facts,
        }
    except Exception as exc:
        return {
            "answer": "",
            "citations": [],
            "structured_facts": {},
            "error": str(exc),
        }


def run_tool_stability_target(inputs: dict[str, Any]) -> dict[str, Any]:
    """Local stability target; it never calls Linear."""
    provider = inputs.get("provider") or LINEAR_PROVIDER
    first_key = build_dispatch_idempotency_key(
        provider=provider,
        draft_id=inputs["draft_id"],
        action_item_id=inputs["action_item_id"],
    )
    second_key = build_dispatch_idempotency_key(
        provider=provider,
        draft_id=inputs["draft_id"],
        action_item_id=inputs["action_item_id"],
    )
    return {
        "provider": provider,
        "idempotency_key": first_key,
        "idempotent": first_key == second_key,
        "created_external_task": False,
    }


def build_qa_seed_preview(case: EvalCase) -> dict[str, Any]:
    """Expose the deterministic eval meeting id for tests and debugging."""
    return {
        "meeting_id": f"eval-{case.case_id}",
        "chunk_count": len(_chunk_eval_raw_content(case.inputs["raw_content"])),
    }


@lru_cache(maxsize=256)
def _seed_eval_meeting_points(*, meeting_id: str, title: str, raw_content: str) -> None:
    chunks = _chunk_eval_raw_content(raw_content)
    if not chunks:
        return
    vectors = embed_texts(chunks)
    points = [
        PointStruct(
            id=str(uuid5(NAMESPACE_URL, f"meeting-eval:{meeting_id}:{index}")),
            vector=vector,
            payload={
                "meeting_id": meeting_id,
                "chunk_id": str(uuid5(NAMESPACE_URL, f"meeting-eval:{meeting_id}:{index}")),
                "chunk_type": "transcript_chunk",
                "source_type": "langsmith_eval",
                "source_id": None,
                "draft_id": None,
                "status": "eval",
                "title": title,
                "text": text,
                "source_excerpt": text[:300],
            },
        )
        for index, (text, vector) in enumerate(zip(chunks, vectors, strict=True))
    ]
    replace_meeting_points(meeting_id=meeting_id, points=points)


def _chunk_eval_raw_content(raw_content: str, *, max_chars: int = 900) -> list[str]:
    paragraphs = [part.strip() for part in raw_content.splitlines() if part.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = f"{current}\n{paragraph}".strip() if current else paragraph
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(current)
        current = paragraph
    if current:
        chunks.append(current)
    return chunks


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))
