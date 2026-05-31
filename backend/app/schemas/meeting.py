from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.audio import AudioSegment
from app.models.meeting import Meeting
from app.schemas.analysis import AnalysisDraftResponse


class MeetingCreateTextRequest(BaseModel):
    """用户粘贴会议纪要时的请求体。"""

    # 用户可选填写的会议标题。
    title: str | None = Field(default=None, max_length=200)
    # 用户粘贴的会议正文，不能为空。
    content: str = Field(min_length=1)
    # 当前粘贴入口只区分普通文本和 Markdown。
    source_type: Literal["text", "markdown"] = "text"
    # 会议真实发生时间，后续解析相对截止时间会用到。
    occurred_at: datetime | None = None


class MeetingContentUpdateRequest(BaseModel):
    """补充或修正会议原文，用于恢复等待输入/澄清的工作流。"""

    # 修正后的完整会议内容；服务端按完整替换处理，避免增量拼接造成重复。
    content: str = Field(min_length=1)
    # 可选同步修改会议标题。
    title: str | None = Field(default=None, max_length=200)
    # 可选同步修改会议发生时间。
    occurred_at: datetime | None = None


class MeetingSummaryResponse(BaseModel):
    """会议创建后的摘要信息，不直接返回整篇原文。"""

    # 会议 ID。
    id: str
    # 会议标题。
    title: str | None
    # 原始内容来源类型。
    source_type: str
    # 当前处理状态。
    status: str
    # 会议发生时间。
    occurred_at: datetime | None
    # 原文字符数，列表页无需拉整篇正文也能展示体量。
    content_length: int
    # 原文预览，默认只截取前一小段。
    content_preview: str
    # 上传或解析入口写入的附加元数据。
    metadata_json: dict[str, Any] | None
    # 会议创建时间。
    created_at: datetime
    # 会议主记录最近更新时间。
    updated_at: datetime

    @classmethod
    def from_model(cls, meeting: Meeting) -> "MeetingSummaryResponse":
        content = meeting.raw_content or ""
        return cls(
            id=meeting.id,
            title=meeting.title,
            source_type=meeting.source_type,
            status=meeting.status,
            occurred_at=meeting.occurred_at,
            content_length=len(content),
            content_preview=_build_content_preview(content),
            metadata_json=meeting.metadata_json,
            created_at=meeting.created_at,
            updated_at=meeting.updated_at,
        )


class MeetingDetailResponse(MeetingSummaryResponse):
    """会议详情接口会返回原文，方便阶段二调试解析结果。"""

    # 完整会议正文。
    raw_content: str | None
    # 当前会议最新一份分析草稿；还没分析时为空。
    analysis_draft: AnalysisDraftResponse | None = None

    @classmethod
    def from_model(
        cls,
        meeting: Meeting,
        analysis_draft: AnalysisDraftResponse | None = None,
    ) -> "MeetingDetailResponse":
        summary = MeetingSummaryResponse.from_model(meeting).model_dump()
        return cls(**summary, raw_content=meeting.raw_content, analysis_draft=analysis_draft)


class MeetingDeleteResponse(BaseModel):
    """删除会议后的确认响应。"""

    # 被删除的会议 ID。
    meeting_id: str
    # 删除结果，当前固定返回 deleted。
    status: str
    # Qdrant 清理结果摘要，方便排查向量点是否同步删除。
    qdrant: dict[str, Any]


class AudioSegmentResponse(BaseModel):
    """会议录音转写片段响应。"""

    id: str
    meeting_id: str
    text: str
    start_time: float | None
    end_time: float | None
    speaker: str | None
    emotion: str | None
    pause_before_ms: int | None
    speech_rate: str | None
    confidence: float | None
    source_filename: str | None
    order_index: int

    @classmethod
    def from_model(cls, segment: AudioSegment) -> "AudioSegmentResponse":
        return cls(
            id=segment.id,
            meeting_id=segment.meeting_id,
            text=segment.text,
            start_time=segment.start_time,
            end_time=segment.end_time,
            speaker=segment.speaker,
            emotion=segment.emotion,
            pause_before_ms=segment.pause_before_ms,
            speech_rate=segment.speech_rate,
            confidence=segment.confidence,
            source_filename=segment.source_filename,
            order_index=segment.order_index,
        )


def _build_content_preview(content: str, limit: int = 120) -> str:
    preview = content.replace("\n", " ").strip()
    if len(preview) <= limit:
        return preview
    return f"{preview[:limit]}..."
