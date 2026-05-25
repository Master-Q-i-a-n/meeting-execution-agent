from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.meeting import Meeting


class WorkflowRun(Base):
    """一次后台工作流运行记录。"""

    __tablename__ = "workflow_runs"

    # 本次工作流运行在系统内的唯一 ID。
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    # 关联会议；有些通用工作流允许不绑定会议。
    meeting_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    # 工作流类别，例如 meeting_execution、external_task_dispatch。
    workflow_type: Mapped[str] = mapped_column(String(64), nullable=False)
    # 当前执行到的节点名，排错时先看这里。
    current_node: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 工作流状态，例如 pending、running、completed、failed。
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False, index=True)
    # 节点间需要保留的附加信息和汇总结果。
    payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # 失败时记录错误摘要，给接口查询和排错使用。
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 当前工作流已经重试过多少次。
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # 工作流运行记录创建时间。
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    # 工作流状态最近更新时间。
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # 回到会议主记录的 ORM 关系。
    meeting: Mapped["Meeting | None"] = relationship(back_populates="workflow_runs")
    # 本次工作流中发生的外部工具调用记录。
    tool_calls: Mapped[list["ToolCall"]] = relationship(
        back_populates="workflow_run",
        cascade="all, delete-orphan",
    )


class ToolCall(Base):
    """一次外部工具调用的审计记录。"""

    __tablename__ = "tool_calls"

    # 工具调用记录的唯一 ID。
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    # 调用属于哪次工作流，便于查看完整执行链。
    workflow_run_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    # 工具名，例如 linear.create_task。
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    # 幂等键；相同业务动作重试时靠它避免重复创建外部对象。
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)
    # 单次工具调用状态，例如 running、succeeded、failed。
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False, index=True)
    # 可审计的请求参数，不应保存 API Key 等秘密。
    request_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # 外部系统返回结果的摘要。
    response_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # 工具调用失败时记录错误摘要。
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 工具调用记录创建时间。
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    # 工具调用状态最近更新时间。
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # 回到所属工作流的 ORM 关系。
    workflow_run: Mapped["WorkflowRun | None"] = relationship(back_populates="tool_calls")
