from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import JSON, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.analysis import AnalysisDraft
    from app.models.audio import AudioSegment
    from app.models.chunk import MeetingChunk
    from app.models.workflow import WorkflowRun


class Meeting(Base):
    """会议原文与解析生命周期的主表。"""

    __tablename__ = "meetings"

    # 会议在本系统中的唯一 ID，后续草稿、工作流和索引都通过它关联。
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    # 用户填写的会议标题；上传文件时允许先不填。
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # 内容来源类型，例如 text、markdown、pdf、docx。
    source_type: Mapped[str] = mapped_column(String(32), default="text", nullable=False)
    # 会议当前处理状态，例如 uploaded、analyzing、draft。
    status: Mapped[str] = mapped_column(String(32), default="uploaded", nullable=False, index=True)
    # 会议实际发生时间，解析“下周三”这类相对截止时间时会作为参照。
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # 解析前保存的会议原文，MySQL 仍是业务事实源。
    raw_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 文件名、大小、解析器等附加元数据。
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # 记录首次入库时间。
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    # 记录最近一次更新会议主记录的时间。
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # 一场会议可以触发多次后台工作流，例如分析和外部派发。
    workflow_runs: Mapped[list["WorkflowRun"]] = relationship(
        back_populates="meeting",
        cascade="all, delete-orphan",
    )
    # 一场会议可多次分析，因此会保留多份草稿记录。
    analysis_drafts: Mapped[list["AnalysisDraft"]] = relationship(
        back_populates="meeting",
        cascade="all, delete-orphan",
    )
    # 会议写入 Qdrant 前在 MySQL 中登记的索引片段。
    meeting_chunks: Mapped[list["MeetingChunk"]] = relationship(
        back_populates="meeting",
        cascade="all, delete-orphan",
    )
    # 会议录音转写得到的语音片段，用于时间戳引用和语气线索。
    audio_segments: Mapped[list["AudioSegment"]] = relationship(
        back_populates="meeting",
        cascade="all, delete-orphan",
        order_by="AudioSegment.order_index",
    )
