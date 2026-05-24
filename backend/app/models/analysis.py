from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.chunk import MeetingChunk
    from app.models.integration import ExternalTaskMapping
    from app.models.meeting import Meeting
    from app.models.reminder import Reminder


class AnalysisDraft(Base):
    """一次会议解析生成的草稿主记录。"""

    __tablename__ = "analysis_drafts"

    # 一次分析草稿在系统中的唯一 ID。
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    # 草稿属于哪场会议。
    meeting_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 执行草稿状态，例如 draft、confirmed、dispatching。
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False, index=True)
    # 生成该草稿的模型名，方便追踪模型切换影响。
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    # 提示词版本，便于评测和回溯解析策略。
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    # LLM 给出的整场会议决策摘要。
    decision_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 经过结构校验后的原始抽取 JSON，确认快照会保留它作为 Agent 建议。
    raw_result_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    # 草稿生成时间。
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    # 草稿状态或内容最近更新时间。
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # 回到会议主记录的 ORM 关系。
    meeting: Mapped["Meeting"] = relationship(back_populates="analysis_drafts")
    # 该草稿下的决策项，按抽取顺序返回。
    decisions: Mapped[list["Decision"]] = relationship(
        back_populates="analysis_draft",
        cascade="all, delete-orphan",
        order_by="Decision.order_index",
    )
    # 该草稿下的待办项，人工审核和 Linear 派发主要处理它。
    action_items: Mapped[list["ActionItem"]] = relationship(
        back_populates="analysis_draft",
        cascade="all, delete-orphan",
        order_by="ActionItem.order_index",
    )
    # 该草稿下识别出的风险项。
    risk_items: Mapped[list["RiskItem"]] = relationship(
        back_populates="analysis_draft",
        cascade="all, delete-orphan",
        order_by="RiskItem.order_index",
    )
    # 该草稿下仍需人工澄清的信息。
    unconfirmed_items: Mapped[list["UnconfirmedItem"]] = relationship(
        back_populates="analysis_draft",
        cascade="all, delete-orphan",
        order_by="UnconfirmedItem.order_index",
    )
    # 用户确认草稿时保存的历史快照。
    confirmation_snapshots: Mapped[list["DraftConfirmationSnapshot"]] = relationship(
        back_populates="analysis_draft",
        cascade="all, delete-orphan",
        order_by="DraftConfirmationSnapshot.created_at",
    )
    # 当前草稿生成并写入 Qdrant 的索引片段映射。
    meeting_chunks: Mapped[list["MeetingChunk"]] = relationship(
        back_populates="analysis_draft",
        cascade="all, delete-orphan",
    )


class DraftItemMixin:
    """决策、待办、风险和未确认项共享的草稿字段。"""

    # 草稿明细项自己的唯一 ID。
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    # 明细项状态，初始都属于待审核草稿。
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False, index=True)
    # 在同类明细中的显示顺序。
    order_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # 会议原文中支撑这条结论的来源片段。
    source_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    # LLM 对这条抽取结果的置信度，范围由上层 schema 约束。
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    # 明细项生成时间。
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    # 明细项最近更新时间。
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Decision(DraftItemMixin, Base):
    """草稿中的单条会议决策。"""

    __tablename__ = "decisions"

    # 所属分析草稿。
    analysis_draft_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("analysis_drafts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 决策正文摘要。
    summary: Mapped[str] = mapped_column(Text, nullable=False)

    # 回到草稿主记录的 ORM 关系。
    analysis_draft: Mapped["AnalysisDraft"] = relationship(back_populates="decisions")


class ActionItem(DraftItemMixin, Base):
    """草稿中的单条可执行待办。"""

    __tablename__ = "action_items"

    # 所属分析草稿。
    analysis_draft_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("analysis_drafts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 待办标题，也是外部任务创建时的标题来源。
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    # 待办补充说明。
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 从会议中抽取或人工修订的负责人姓名。
    owner_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # 会议原话里的截止时间表达，例如“本周五下班前”。
    deadline_text: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # 可确定时落成标准时间；无法确定时保留为空。
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # 人工确认时设置的优先级，例如 low、medium、high、urgent。
    priority: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # 回到草稿主记录的 ORM 关系。
    analysis_draft: Mapped["AnalysisDraft"] = relationship(back_populates="action_items")
    # 该待办已创建到哪些外部任务系统。
    external_task_mappings: Mapped[list["ExternalTaskMapping"]] = relationship(
        back_populates="action_item",
        cascade="all, delete-orphan",
        order_by="ExternalTaskMapping.created_at",
    )
    # 这条待办生成的应用内提醒。
    reminders: Mapped[list["Reminder"]] = relationship(
        back_populates="action_item",
        cascade="all, delete-orphan",
        order_by="Reminder.triggered_at",
    )


class RiskItem(DraftItemMixin, Base):
    """草稿中的风险提示。"""

    __tablename__ = "risk_items"

    # 所属分析草稿。
    analysis_draft_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("analysis_drafts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 风险标题。
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    # 风险说明。
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 回到草稿主记录的 ORM 关系。
    analysis_draft: Mapped["AnalysisDraft"] = relationship(back_populates="risk_items")


class UnconfirmedItem(DraftItemMixin, Base):
    """草稿中仍需用户澄清的问题。"""

    __tablename__ = "unconfirmed_items"

    # 所属分析草稿。
    analysis_draft_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("analysis_drafts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 需要确认的问题本身。
    question: Mapped[str] = mapped_column(Text, nullable=False)
    # 为什么需要确认或它的上下文说明。
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 回到草稿主记录的 ORM 关系。
    analysis_draft: Mapped["AnalysisDraft"] = relationship(back_populates="unconfirmed_items")


class DraftConfirmationSnapshot(Base):
    """用户确认执行草案时保存的快照。"""

    __tablename__ = "draft_confirmation_snapshots"

    # 快照记录在系统内的唯一 ID。
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    # 这次确认对应哪份分析草稿。
    analysis_draft_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("analysis_drafts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 确认前的 Agent 原始建议。
    agent_suggestion_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    # 用户编辑并确认后的最终草稿内容。
    confirmed_draft_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    # 用户确认发生的时间。
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    # 回到被确认草稿的 ORM 关系。
    analysis_draft: Mapped["AnalysisDraft"] = relationship(
        back_populates="confirmation_snapshots"
    )
