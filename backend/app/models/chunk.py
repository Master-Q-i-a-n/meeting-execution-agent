from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.analysis import AnalysisDraft
    from app.models.meeting import Meeting


class MeetingChunk(Base):
    """MySQL 中的会议语义索引映射。

    Qdrant 保存向量；这里保存 point 对应的业务来源和重建状态。
    """

    __tablename__ = "meeting_chunks"

    # 每个索引片段在 MySQL 中的唯一 ID。
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    # 片段所属会议，用于跨草稿追溯原始来源。
    meeting_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 决策/待办片段来自某次分析草稿；原文片段可以为空。
    analysis_draft_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("analysis_drafts.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    # 来源类别，例如 transcript、decision、action_item。
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # 来源对象 ID；决策和待办会存对应表主键，原文分块通常为空。
    source_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    # 同一来源下的分块顺序，便于按原文顺序重排。
    chunk_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # 实际送去做 embedding 和检索展示的文本。
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # Qdrant 中 point 的稳定 ID，用于更新或删除同一向量点。
    qdrant_point_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    # 向量索引状态，例如 pending、indexed、failed。
    index_status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False, index=True)
    # 索引失败时记录错误，方便后续重建排查。
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 片段映射首次创建时间。
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    # 片段状态或错误信息最近更新时间。
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # 回到会议主记录的 ORM 关系。
    meeting: Mapped["Meeting"] = relationship(back_populates="meeting_chunks")
    # 回到分析草稿的 ORM 关系；原文分块可能没有草稿来源。
    analysis_draft: Mapped["AnalysisDraft | None"] = relationship(back_populates="meeting_chunks")
