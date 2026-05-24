from typing import Any

from pydantic import BaseModel, Field


class MeetingAskRequest(BaseModel):
    """会后追问请求体。"""

    # 用户提出的问题。
    question: str = Field(min_length=1)
    # 语义检索最多召回多少条会议片段。
    top_k: int = Field(default=5, ge=1, le=20)


class MeetingCitationResponse(BaseModel):
    """回答中引用的会议来源。"""

    meeting_id: str | None
    chunk_id: str | None
    chunk_type: str | None
    source_id: str | None
    text: str | None
    source_excerpt: str | None
    score: float | None


class MeetingAskResponse(BaseModel):
    """会后追问响应。"""

    # 百炼基于检索证据生成的回答。
    answer: str
    # 回答依据，前端可以展示来源会议和片段。
    citations: list[MeetingCitationResponse]
    # 从 MySQL 查到的结构化事实，例如待办、决策、会议标题。
    structured_facts: dict[str, Any]
