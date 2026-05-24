from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logger import get_logger
from app.db.session import async_session_factory
from app.integrations.linear import LINEAR_PROVIDER, LinearTaskDispatchAdapter
from app.integrations.tasks import TaskDispatchAdapter
from app.models.analysis import ActionItem, AnalysisDraft
from app.models.integration import ExternalTaskMapping
from app.models.workflow import ToolCall, WorkflowRun

logger = get_logger(__name__)

DISPATCHABLE_DRAFT_STATUSES = {"confirmed", "failed"}


class ExternalTaskDispatchError(RuntimeError):
    """已确认草案不能开始当前外部派发流程。"""


@dataclass(frozen=True)
class ExternalTaskDispatchResult:
    draft_id: str
    workflow_run_id: str
    status: str
    succeeded_count: int
    skipped_count: int
    failed_count: int


def ensure_draft_can_dispatch(draft: AnalysisDraft) -> None:
    """只有确认后的草案或失败后待重试草案能发往外部系统。"""
    if draft.status not in DISPATCHABLE_DRAFT_STATUSES:
        raise ExternalTaskDispatchError(
            f"draft status {draft.status} cannot be dispatched"
        )


def build_dispatch_idempotency_key(
    *,
    provider: str,
    draft_id: str,
    action_item_id: str,
) -> str:
    """同一待办发往同一平台时生成稳定幂等键。"""
    return f"{provider}:dispatch:{draft_id}:{action_item_id}"


def get_task_dispatch_adapter(provider: str) -> TaskDispatchAdapter:
    # 目前 Linear 是真实集成；后续平台会继续挂在同一 adapter 边界下。
    if provider == LINEAR_PROVIDER:
        return LinearTaskDispatchAdapter()
    raise ExternalTaskDispatchError(f"unsupported dispatch provider: {provider}")


async def run_external_task_dispatch(
    *,
    draft_id: str,
    workflow_run_id: str,
    provider: str = LINEAR_PROVIDER,
    adapter: TaskDispatchAdapter | None = None,
) -> ExternalTaskDispatchResult:
    """在 worker 中逐条派发确认后的 action item。"""
    dispatch_adapter = adapter or get_task_dispatch_adapter(provider)
    logger.info(
        "外部任务派发开始 draft_id=%s workflow_run_id=%s provider=%s",
        draft_id,
        workflow_run_id,
        dispatch_adapter.provider,
    )
    async with async_session_factory() as db:
        draft = await _load_dispatch_draft(db, draft_id)
        workflow = await db.get(WorkflowRun, workflow_run_id)
        if draft is None:
            raise ExternalTaskDispatchError("analysis draft not found")
        if workflow is None:
            raise ExternalTaskDispatchError("dispatch workflow run not found")

        ensure_draft_can_dispatch(draft)
        # 在真正调用外部系统前先写入运行态，接口查询时能看到派发已经开始。
        draft.status = "dispatching"
        workflow.status = "running"
        workflow.current_node = "dispatch_tasks"
        await db.commit()
        logger.info(
            "外部任务派发进入运行状态 draft_id=%s workflow_run_id=%s action_item_count=%s",
            draft.id,
            workflow.id,
            len(draft.action_items),
        )

        succeeded_count = 0
        skipped_count = 0
        failed_count = 0
        errors: list[str] = []

        # 单条待办失败不提前终止整批派发，已成功项会保留映射供重派跳过。
        for action_item in draft.action_items:
            outcome, error_message = await _dispatch_action_item(
                db=db,
                workflow=workflow,
                draft=draft,
                action_item=action_item,
                adapter=dispatch_adapter,
            )
            if outcome == "succeeded":
                succeeded_count += 1
            elif outcome == "skipped":
                skipped_count += 1
            else:
                failed_count += 1
                if error_message:
                    errors.append(error_message)

        if failed_count:
            # 任一待办失败时草稿进入 failed，用户可从手动 dispatch 入口重试。
            draft.status = "failed"
            workflow.status = "failed"
            workflow.error_message = "; ".join(errors)
        else:
            draft.status = "completed"
            workflow.status = "completed"
            workflow.error_message = None
        workflow.current_node = "finish"
        workflow.payload_json = {
            **(workflow.payload_json or {}),
            "provider": dispatch_adapter.provider,
            "draft_id": draft.id,
            "succeeded_count": succeeded_count,
            "skipped_count": skipped_count,
            "failed_count": failed_count,
        }
        await db.commit()
        logger.info(
            "外部任务派发完成 draft_id=%s workflow_run_id=%s status=%s succeeded=%s skipped=%s failed=%s",
            draft.id,
            workflow.id,
            workflow.status,
            succeeded_count,
            skipped_count,
            failed_count,
        )
        return ExternalTaskDispatchResult(
            draft_id=draft.id,
            workflow_run_id=workflow.id,
            status=workflow.status,
            succeeded_count=succeeded_count,
            skipped_count=skipped_count,
            failed_count=failed_count,
        )


async def _load_dispatch_draft(db: AsyncSession, draft_id: str) -> AnalysisDraft | None:
    statement = (
        select(AnalysisDraft)
        .options(
            selectinload(AnalysisDraft.action_items).selectinload(
                ActionItem.external_task_mappings
            )
        )
        .where(AnalysisDraft.id == draft_id)
    )
    return (await db.execute(statement)).scalars().first()


async def _dispatch_action_item(
    *,
    db: AsyncSession,
    workflow: WorkflowRun,
    draft: AnalysisDraft,
    action_item: ActionItem,
    adapter: TaskDispatchAdapter,
) -> tuple[str, str | None]:
    idempotency_key = build_dispatch_idempotency_key(
        provider=adapter.provider,
        draft_id=draft.id,
        action_item_id=action_item.id,
    )
    # 成功映射是最可靠的“已经建过外部任务”证据，重试时直接跳过远程创建。
    mapping = await db.scalar(
        select(ExternalTaskMapping).where(
            ExternalTaskMapping.provider == adapter.provider,
            ExternalTaskMapping.action_item_id == action_item.id,
            ExternalTaskMapping.status == "succeeded",
        )
    )
    if mapping is not None:
        action_item.status = "dispatched"
        await db.commit()
        logger.info(
            "外部任务派发跳过已有成功映射 action_item_id=%s provider=%s external_task_id=%s",
            action_item.id,
            adapter.provider,
            mapping.external_task_id,
        )
        return "skipped", None

    # tool_call 幂等键兜底：即使映射查询不到，也不重复执行成功过的同一业务动作。
    tool_call = await db.scalar(select(ToolCall).where(ToolCall.idempotency_key == idempotency_key))
    if tool_call is not None and tool_call.status == "succeeded":
        action_item.status = "dispatched"
        await db.commit()
        logger.info(
            "外部任务派发跳过已有成功工具调用 action_item_id=%s provider=%s tool_call_id=%s",
            action_item.id,
            adapter.provider,
            tool_call.id,
        )
        return "skipped", None
    if tool_call is not None and tool_call.status == "running":
        # 还在 running 表示可能已有另一个 worker 正在处理，当前任务先报失败等待重派。
        error_message = f"dispatch still running for action item {action_item.id}"
        logger.warning(
            "外部任务派发发现运行中的幂等调用 action_item_id=%s provider=%s tool_call_id=%s",
            action_item.id,
            adapter.provider,
            tool_call.id,
        )
        return "failed", error_message

    request_json = adapter.build_create_request(action_item)
    # 外部调用前先落 running 审计记录；worker 中途崩掉时也能看见调用走到了哪里。
    if tool_call is None:
        tool_call = ToolCall(
            workflow_run_id=workflow.id,
            tool_name=f"{adapter.provider}.create_task",
            idempotency_key=idempotency_key,
            status="running",
            request_json=request_json,
        )
        db.add(tool_call)
    else:
        tool_call.workflow_run_id = workflow.id
        tool_call.status = "running"
        tool_call.request_json = request_json
        tool_call.error_message = None
    await db.commit()
    await db.refresh(tool_call)
    logger.info(
        "外部任务派发调用开始 action_item_id=%s provider=%s tool_call_id=%s",
        action_item.id,
        adapter.provider,
        tool_call.id,
    )

    try:
        result = adapter.create_task(action_item)
    except Exception as exc:
        # 远程调用失败时保留请求与错误，方便用户判断是配置、网络还是平台返回失败。
        error_message = str(exc)
        tool_call.status = "failed"
        tool_call.error_message = error_message
        await db.commit()
        logger.exception(
            "外部任务派发调用失败 action_item_id=%s provider=%s tool_call_id=%s error=%s",
            action_item.id,
            adapter.provider,
            tool_call.id,
            error_message,
        )
        return "failed", error_message

    # 远程任务创建成功后，同时补响应审计和本地到外部对象的映射。
    tool_call.status = "succeeded"
    tool_call.response_json = result.response_json
    tool_call.error_message = None
    action_item.status = "dispatched"
    db.add(
        ExternalTaskMapping(
            action_item_id=action_item.id,
            tool_call_id=tool_call.id,
            provider=result.provider,
            external_task_id=result.external_task_id,
            external_identifier=result.external_identifier,
            external_url=result.external_url,
            status="succeeded",
        )
    )
    await db.commit()
    logger.info(
        "外部任务派发调用成功 action_item_id=%s provider=%s external_identifier=%s",
        action_item.id,
        result.provider,
        result.external_identifier,
    )
    return "succeeded", None
