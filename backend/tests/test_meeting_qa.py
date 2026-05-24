from types import SimpleNamespace

import pytest

from app.retrieval.qdrant_store import SemanticSearchPoint
from app.services.meeting_qa import (
    NO_EVIDENCE_ANSWER,
    answer_meeting_question,
    build_citations,
)


def test_build_citations_keeps_qdrant_payload_links() -> None:
    citations = build_citations(
        [
            SemanticSearchPoint(
                point_id="point-1",
                score=0.87,
                payload={
                    "meeting_id": "meeting-1",
                    "chunk_id": "chunk-1",
                    "chunk_type": "action_item",
                    "source_id": "action-1",
                    "text": "待办：完成联调",
                    "source_excerpt": "张三负责联调",
                },
            )
        ]
    )

    assert citations[0]["meeting_id"] == "meeting-1"
    assert citations[0]["chunk_id"] == "chunk-1"
    assert citations[0]["source_id"] == "action-1"
    assert citations[0]["score"] == 0.87


@pytest.mark.asyncio
async def test_answer_meeting_question_returns_no_evidence_without_search_results() -> None:
    async_session = SimpleNamespace(execute=None)

    result = await answer_meeting_question(
        db=async_session,  # type: ignore[arg-type]
        question="谁负责联调？",
        top_k=5,
        embedder=lambda texts: [[0.1, 0.2]],
        searcher=lambda **kwargs: [],
        answer_generator=lambda **kwargs: "不应该调用",
    )

    assert result["answer"] == NO_EVIDENCE_ANSWER
    assert result["citations"] == []
    assert result["structured_facts"] == {
        "meetings": [],
        "decisions": [],
        "action_items": [],
    }


@pytest.mark.asyncio
async def test_answer_meeting_question_passes_citations_to_answer_generator() -> None:
    class FakeSession:
        async def execute(self, _statement):
            return SimpleNamespace(
                all=lambda: [],
                scalars=lambda: SimpleNamespace(all=lambda: []),
            )

    def fake_answer_generator(**kwargs):
        assert kwargs["question"] == "谁负责联调？"
        assert kwargs["citations"][0]["chunk_id"] == "chunk-1"
        return "张三负责联调。[1]"

    result = await answer_meeting_question(
        db=FakeSession(),  # type: ignore[arg-type]
        question="谁负责联调？",
        top_k=5,
        embedder=lambda texts: [[0.1, 0.2]],
        searcher=lambda **kwargs: [
            SemanticSearchPoint(
                point_id="chunk-1",
                score=0.9,
                payload={
                    "meeting_id": "meeting-1",
                    "chunk_id": "chunk-1",
                    "chunk_type": "transcript_chunk",
                    "text": "张三负责联调",
                },
            )
        ],
        answer_generator=fake_answer_generator,
    )

    assert result["answer"] == "张三负责联调。[1]"
    assert result["citations"][0]["text"] == "张三负责联调"
