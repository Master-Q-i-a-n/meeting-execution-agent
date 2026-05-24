from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.analysis import ActionItem


class Reminder(Base):
    """应用内提醒记录。

    v1 只把提醒写入 MySQL，桌面端后续通过接口展示；邮件、飞书等渠道以后再扩展。
    """

    __tablename__ = "reminders"

    # 提醒记录在系统内的唯一 ID。
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    # 提醒对应哪条本地待办。
    action_item_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("action_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 提醒类型：upcoming 表示即将到期，overdue 表示已经逾期。
    reminder_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # 提醒状态：unread/read。
    status: Mapped[str] = mapped_column(String(32), default="unread", nullable=False, index=True)
    # 展示给用户看的提醒文案。
    message: Mapped[str] = mapped_column(Text, nullable=False)
    # 待办截止时间快照，避免后续待办变更后看不出提醒当时基于哪个时间生成。
    due_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    # 扫描任务生成提醒的时间。
    triggered_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    # 用户读取提醒的时间，未读时为空。
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # 幂等键，避免 Celery Beat 重复扫描时插入重复提醒。
    unique_key: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    # 预留错误摘要字段，后续如果提醒发送到外部渠道失败可以记录。
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 提醒记录创建时间。
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    # 提醒记录最近更新时间。
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # 回到本地待办的 ORM 关系。
    action_item: Mapped["ActionItem"] = relationship(back_populates="reminders")
