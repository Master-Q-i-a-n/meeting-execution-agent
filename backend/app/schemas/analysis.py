from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.analysis import ActionItem, AnalysisDraft, DraftConfirmationSnapshot
from app.models.integration import ExternalTaskMapping

ActionItemPriority = Literal["low", "medium", "high", "urgent"]


class ExtractedDecision(BaseModel):
    """LLM 从会议中抽出的决策项。"""

    # 决策摘要正文。
    summary: str = Field(min_length=1)
    # 支撑这条决策的会议原文片段。
    source_excerpt: str | None = None
    # 模型对抽取结果的置信度，取值范围 0-1。
    confidence: float | None = Field(default=None, ge=0, le=1)


class ExtractedActionItem(BaseModel):
    """LLM 抽出的待办，仍属于等待人工确认的草稿。"""

    # 待办标题。
    title: str = Field(min_length=1)
    # 待办补充说明。
    description: str | None = None
    # 会议中提到的负责人姓名。
    owner_name: str | None = None
    # 会议原话中的截止时间表达。
    deadline_text: str | None = None
    # 可解析成标准时间时写入这里。
    due_at: datetime | None = None
    # 支撑这条待办的会议原文片段。
    source_excerpt: str | None = None
    # 模型对抽取结果的置信度，取值范围 0-1。
    confidence: float | None = Field(default=None, ge=0, le=1)


class ExtractedRiskItem(BaseModel):
    """LLM 从会议中抽出的风险项。"""

    # 风险标题。
    title: str = Field(min_length=1)
    # 风险的补充说明。
    description: str | None = None
    # 支撑风险判断的会议原文片段。
    source_excerpt: str | None = None
    # 模型对抽取结果的置信度，取值范围 0-1。
    confidence: float | None = Field(default=None, ge=0, le=1)


class ExtractedUnconfirmedItem(BaseModel):
    """LLM 认为仍需用户补充或澄清的信息。"""

    # 要向用户确认的问题。
    question: str = Field(min_length=1)
    # 问题的补充上下文。
    description: str | None = None
    # 触发该疑问的会议原文片段。
    source_excerpt: str | None = None
    # 模型对抽取结果的置信度，取值范围 0-1。
    confidence: float | None = Field(default=None, ge=0, le=1)


class MeetingDraftExtraction(BaseModel):
    """百炼 JSON 输出最终要满足的结构。"""

    # 整场会议的决策摘要。
    decision_summary: str = ""
    # 从会议中抽取的决策列表。
    decisions: list[ExtractedDecision] = Field(default_factory=list)
    # 从会议中抽取的待办列表。
    action_items: list[ExtractedActionItem] = Field(default_factory=list)
    # 从会议中抽取的风险列表。
    risk_items: list[ExtractedRiskItem] = Field(default_factory=list)
    # 从会议中抽取的待澄清列表。
    unconfirmed_items: list[ExtractedUnconfirmedItem] = Field(default_factory=list)


class DecisionDraftResponse(BaseModel):
    """返回给调用方的单条决策草稿。"""

    # 决策记录 ID。
    id: str
    # 决策摘要正文。
    summary: str
    # 会议原文来源片段。
    source_excerpt: str | None
    # 抽取置信度。
    confidence: float | None
    # 决策草稿状态。
    status: str


class ActionItemDraftResponse(BaseModel):
    """返回给调用方的单条待办草稿。"""

    # 待办记录 ID。
    id: str
    # 待办标题。
    title: str
    # 待办补充说明。
    description: str | None
    # 负责人姓名。
    owner_name: str | None
    # 会议原话中的截止时间。
    deadline_text: str | None
    # 标准化后的截止时间。
    due_at: datetime | None
    # 人工确认后的优先级。
    priority: str | None
    # 会议原文来源片段。
    source_excerpt: str | None
    # 抽取置信度。
    confidence: float | None
    # 待办本地状态。
    status: str
    # 已派发到外部系统的任务映射。
    external_tasks: list["ExternalTaskMappingResponse"]

    @classmethod
    def from_model(cls, item: ActionItem) -> "ActionItemDraftResponse":
        return cls(
            id=item.id,
            title=item.title,
            description=item.description,
            owner_name=item.owner_name,
            deadline_text=item.deadline_text,
            due_at=item.due_at,
            priority=item.priority,
            source_excerpt=item.source_excerpt,
            confidence=item.confidence,
            status=item.status,
            external_tasks=[
                ExternalTaskMappingResponse.from_model(mapping)
                for mapping in item.external_task_mappings
            ],
        )


class ActionItemBoardResponse(ActionItemDraftResponse):
    """执行看板列表里的待办，额外带上所属草稿和会议 ID。"""

    analysis_draft_id: str
    meeting_id: str

    @classmethod
    def from_model(cls, item: ActionItem) -> "ActionItemBoardResponse":
        base = ActionItemDraftResponse.from_model(item).model_dump()
        return cls(
            **base,
            analysis_draft_id=item.analysis_draft_id,
            meeting_id=item.analysis_draft.meeting_id,
        )


class ExternalTaskMappingResponse(BaseModel):
    """本地待办与外部任务对象的映射响应。"""

    # 映射记录 ID。
    id: str
    # 外部系统名称，例如 linear。
    provider: str
    # 外部系统真实对象 ID。
    external_task_id: str
    # 外部系统给用户看的编号，例如 MEE-10。
    external_identifier: str | None
    # 外部任务详情页地址。
    external_url: str | None
    # 当前外部映射状态。
    status: str
    # 失败时的错误摘要。
    error_message: str | None
    # 映射创建时间。
    created_at: datetime

    @classmethod
    def from_model(cls, mapping: ExternalTaskMapping) -> "ExternalTaskMappingResponse":
        return cls(
            id=mapping.id,
            provider=mapping.provider,
            external_task_id=mapping.external_task_id,
            external_identifier=mapping.external_identifier,
            external_url=mapping.external_url,
            status=mapping.status,
            error_message=mapping.error_message,
            created_at=mapping.created_at,
        )


class RiskItemDraftResponse(BaseModel):
    """返回给调用方的单条风险草稿。"""

    # 风险记录 ID。
    id: str
    # 风险标题。
    title: str
    # 风险补充说明。
    description: str | None
    # 会议原文来源片段。
    source_excerpt: str | None
    # 抽取置信度。
    confidence: float | None
    # 风险草稿状态。
    status: str


class UnconfirmedItemDraftResponse(BaseModel):
    """返回给调用方的单条待澄清信息。"""

    # 待澄清记录 ID。
    id: str
    # 需要用户确认的问题。
    question: str
    # 问题补充说明。
    description: str | None
    # 会议原文来源片段。
    source_excerpt: str | None
    # 抽取置信度。
    confidence: float | None
    # 待澄清项状态。
    status: str


class AnalysisDraftResponse(BaseModel):
    """会议分析草稿详情响应。"""

    # 草稿 ID。
    id: str
    # 草稿生命周期状态。
    status: str
    # 生成草稿使用的模型名。
    model_name: str
    # 生成草稿使用的提示词版本。
    prompt_version: str
    # 整场会议的决策摘要。
    decision_summary: str | None
    # 决策草稿列表。
    decisions: list[DecisionDraftResponse]
    # 待办草稿列表。
    action_items: list[ActionItemDraftResponse]
    # 风险草稿列表。
    risk_items: list[RiskItemDraftResponse]
    # 待澄清草稿列表。
    unconfirmed_items: list[UnconfirmedItemDraftResponse]
    # 草稿生成时间。
    created_at: datetime
    # 草稿最近更新时间。
    updated_at: datetime

    @classmethod
    def from_model(cls, draft: AnalysisDraft) -> "AnalysisDraftResponse":
        return cls(
            id=draft.id,
            status=draft.status,
            model_name=draft.model_name,
            prompt_version=draft.prompt_version,
            decision_summary=draft.decision_summary,
            decisions=[
                DecisionDraftResponse(
                    id=item.id,
                    summary=item.summary,
                    source_excerpt=item.source_excerpt,
                    confidence=item.confidence,
                    status=item.status,
                )
                for item in draft.decisions
            ],
            action_items=[
                ActionItemDraftResponse.from_model(item)
                for item in draft.action_items
            ],
            risk_items=[
                RiskItemDraftResponse(
                    id=item.id,
                    title=item.title,
                    description=item.description,
                    source_excerpt=item.source_excerpt,
                    confidence=item.confidence,
                    status=item.status,
                )
                for item in draft.risk_items
            ],
            unconfirmed_items=[
                UnconfirmedItemDraftResponse(
                    id=item.id,
                    question=item.question,
                    description=item.description,
                    source_excerpt=item.source_excerpt,
                    confidence=item.confidence,
                    status=item.status,
                )
                for item in draft.unconfirmed_items
            ],
            created_at=draft.created_at,
            updated_at=draft.updated_at,
        )


class MeetingAnalyzeResponse(BaseModel):
    """触发会议分析后立即返回的后台任务信息。"""

    # 被分析的会议 ID。
    meeting_id: str
    # 本次分析工作流 ID。
    workflow_run_id: str
    # Celery 任务 ID。
    task_id: str
    # Celery 投递后的初始状态。
    status: str


class ActionItemDraftUpdateRequest(BaseModel):
    """人工审核时可编辑的执行待办字段。"""

    # 修改后的待办标题。
    title: str | None = Field(default=None, min_length=1, max_length=300)
    # 修改后的待办说明。
    description: str | None = None
    # 修改后的负责人姓名。
    owner_name: str | None = Field(default=None, max_length=200)
    # 修改后的原文式截止时间表达。
    deadline_text: str | None = Field(default=None, max_length=200)
    # 修改后的标准化截止时间。
    due_at: datetime | None = None
    # 修改后的优先级。
    priority: ActionItemPriority | None = None


class DraftStatusUpdateRequest(BaseModel):
    """外部派发阶段推进执行草案状态时使用。"""

    # 目标草稿状态，只允许状态机认可的派发阶段状态。
    status: Literal["dispatching", "completed", "failed"]


class DraftConfirmationSnapshotResponse(BaseModel):
    """用户确认草稿后返回的快照信息。"""

    # 快照记录 ID。
    id: str
    # 被确认的草稿 ID。
    analysis_draft_id: str
    # 确认前的 Agent 建议。
    agent_suggestion_json: dict[str, Any]
    # 用户确认后的草稿内容。
    confirmed_draft_json: dict[str, Any]
    # 快照创建时间，也就是确认发生时间。
    created_at: datetime

    @classmethod
    def from_model(
        cls,
        snapshot: DraftConfirmationSnapshot,
    ) -> "DraftConfirmationSnapshotResponse":
        return cls(
            id=snapshot.id,
            analysis_draft_id=snapshot.analysis_draft_id,
            agent_suggestion_json=snapshot.agent_suggestion_json,
            confirmed_draft_json=snapshot.confirmed_draft_json,
            created_at=snapshot.created_at,
        )


class DraftConfirmationResponse(BaseModel):
    """确认草稿后的响应。"""

    # 已切换为 confirmed 的草稿详情。
    draft: AnalysisDraftResponse
    # 本次确认保存的快照。
    snapshot: DraftConfirmationSnapshotResponse
    # 自动派发投递结果；自动派发关闭时可为空。
    dispatch: "DraftDispatchResponse | None" = None


class DraftDispatchResponse(BaseModel):
    """草稿派发任务投递后的响应。"""

    # 要派发的草稿 ID。
    draft_id: str
    # 本次外部任务派发工作流 ID。
    workflow_run_id: str
    # Celery 派发任务 ID。
    task_id: str
    # Celery 投递后的初始状态。
    status: str
