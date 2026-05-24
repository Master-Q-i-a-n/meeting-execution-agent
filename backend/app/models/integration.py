from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.analysis import ActionItem
    from app.models.workflow import ToolCall


class ExternalTaskMapping(Base):
    """本地待办与外部任务对象的映射。"""

    __tablename__ = "external_task_mappings"
    __table_args__ = (
        UniqueConstraint("provider", "action_item_id", name="uq_external_task_provider_item"),
    )

    # 外部任务映射记录在本系统中的唯一 ID。
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    # 哪个本地 action item 被派发到了外部系统。
    action_item_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("action_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 创建外部任务时对应的 tool call 审计记录。
    tool_call_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tool_calls.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 外部系统名称，例如 linear。
    provider: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # 外部系统的真实对象 ID，例如 Linear Issue ID。
    external_task_id: Mapped[str] = mapped_column(String(128), nullable=False)
    # 外部系统给人看的编号，例如 Linear 的 MEE-10。
    external_identifier: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # 外部任务详情页地址，桌面端可用它跳转。
    external_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 映射状态，当前 v1 成功创建时写 succeeded。
    status: Mapped[str] = mapped_column(String(32), default="succeeded", nullable=False, index=True)
    # 映射层失败摘要，预留给后续状态同步或修复任务使用。
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 外部映射首次写入时间。
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    # 外部映射最近更新时间。
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # 回到本地待办的 ORM 关系。
    action_item: Mapped["ActionItem"] = relationship(back_populates="external_task_mappings")
    # 回到当次外部工具调用审计记录。
    tool_call: Mapped["ToolCall"] = relationship()
