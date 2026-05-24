from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

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


def _build_content_preview(content: str, limit: int = 120) -> str:
    preview = content.replace("\n", " ").strip()
    if len(preview) <= limit:
        return preview
    return f"{preview[:limit]}..."
