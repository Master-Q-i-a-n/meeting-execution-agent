from app.models.analysis import ActionItem, AnalysisDraft, Decision
from app.models.audio import AudioSegment
from app.models.chunk import MeetingChunk
from app.models.meeting import Meeting
from app.services.meeting_indexing import (
    IndexDocument,
    build_index_documents,
    build_qdrant_points,
    chunk_meeting_content,
)


def test_chunk_meeting_content_keeps_paragraph_order() -> None:
    """第一版分块优先保留段落和列表项顺序。"""
    chunks = chunk_meeting_content(
        "项目周会\n\n- 张三负责接口\n- 李四负责测试\n\n风险：依赖外部系统",
        max_chars=20,
        overlap_chars=0,
    )

    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))
    assert chunks[0].text == "项目周会"
    assert "- 张三负责接口" in "\n".join(chunk.text for chunk in chunks)
    assert "风险" in chunks[-1].text


def test_build_index_documents_covers_transcript_decision_and_action_item() -> None:
    meeting = Meeting(id="meeting-1", raw_content="原文段落")
    draft = AnalysisDraft(id="draft-1", meeting_id=meeting.id, status="draft")
    draft.decisions = [Decision(id="decision-1", summary="决定继续推进")]
    draft.action_items = [
        ActionItem(
            id="action-1",
            title="完成接口",
            owner_name="张三",
            deadline_text="周五",
        )
    ]

    documents = build_index_documents(meeting, draft)

    assert [document.source_type for document in documents] == [
        "transcript",
        "decision",
        "action_item",
    ]
    assert "负责人：张三" in documents[-1].text


def test_build_index_documents_uses_audio_segments_for_audio_meeting() -> None:
    meeting = Meeting(id="meeting-1", source_type="audio", raw_content="拼接后的音频转写")
    draft = AnalysisDraft(id="draft-1", meeting_id=meeting.id, status="draft")
    draft.decisions = []
    draft.action_items = []
    segment = AudioSegment(
        id="segment-1",
        meeting_id=meeting.id,
        text="张三负责接口联调。",
        start_time=12.0,
        end_time=18.0,
        emotion="neutral",
        pause_before_ms=800,
        speech_rate="normal",
        source_filename="meeting.mp3",
        order_index=0,
    )

    documents = build_index_documents(meeting, draft, audio_segments=[segment])

    assert len(documents) == 1
    assert documents[0].source_type == "audio_transcript"
    assert documents[0].source_id == "segment-1"
    assert documents[0].metadata["start_time"] == 12.0
    assert documents[0].metadata["source_type"] == "audio"


def test_build_qdrant_points_keeps_business_payload_links() -> None:
    chunk = MeetingChunk(
        id="chunk-1",
        meeting_id="meeting-1",
        source_type="decision",
        source_id="decision-1",
        chunk_index=0,
        text="决策：继续推进",
        qdrant_point_id="chunk-1",
        index_status="pending",
    )
    document = IndexDocument(
        source_type="decision",
        source_id="decision-1",
        analysis_draft_id="draft-1",
        chunk_index=0,
        text=chunk.text,
        source_excerpt="继续推进",
    )

    point = build_qdrant_points(
        meeting_id="meeting-1",
        draft_status="draft",
        chunks=[chunk],
        documents=[document],
        vectors=[[0.1, 0.2]],
    )[0]

    assert point.id == "chunk-1"
    assert point.payload["chunk_id"] == "chunk-1"
    assert point.payload["draft_id"] == "draft-1"
    assert point.payload["chunk_type"] == "decision"


def test_build_qdrant_points_keeps_audio_payload_metadata() -> None:
    chunk = MeetingChunk(
        id="chunk-1",
        meeting_id="meeting-1",
        source_type="audio_transcript",
        source_id="segment-1",
        chunk_index=0,
        text="张三负责接口联调。",
        qdrant_point_id="chunk-1",
        index_status="pending",
    )
    document = IndexDocument(
        source_type="audio_transcript",
        source_id="segment-1",
        analysis_draft_id=None,
        chunk_index=0,
        text=chunk.text,
        source_excerpt=chunk.text,
        metadata={
            "source_type": "audio",
            "start_time": 12.0,
            "end_time": 18.0,
            "emotion": "neutral",
            "pause_before_ms": 800,
            "speech_rate": "normal",
            "source_filename": "meeting.mp3",
        },
    )

    point = build_qdrant_points(
        meeting_id="meeting-1",
        draft_status="draft",
        chunks=[chunk],
        documents=[document],
        vectors=[[0.1, 0.2]],
    )[0]

    assert point.payload["chunk_type"] == "audio_transcript"
    assert point.payload["source_type"] == "audio"
    assert point.payload["start_time"] == 12.0
    assert point.payload["source_filename"] == "meeting.mp3"
