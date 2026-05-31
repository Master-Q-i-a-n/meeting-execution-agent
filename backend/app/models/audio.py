from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.meeting import Meeting


class AudioSegment(Base):
    """会议录音 ASR 后的可追溯语音片段。"""

    __tablename__ = "audio_segments"

    # 语音片段在系统内的唯一 ID。
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    # 片段所属会议。
    meeting_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # ASR 返回的转写文本。
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # 片段开始时间，单位秒。
    start_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    # 片段结束时间，单位秒。
    end_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    # 说话人标签，第一版只保存 ASR 返回的匿名 speaker。
    speaker: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # ASR 或音频模型返回的表达情绪线索。
    emotion: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 与上一段之间的停顿时间，单位毫秒。
    pause_before_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 粗粒度语速标签：slow / normal / fast。
    speech_rate: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # ASR 置信度。
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    # 上传时的原始文件名。
    source_filename: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # 同一会议内的片段顺序。
    order_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # 片段创建时间。
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    # 片段最近更新时间。
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # 回到会议主记录。
    meeting: Mapped["Meeting"] = relationship(back_populates="audio_segments")
