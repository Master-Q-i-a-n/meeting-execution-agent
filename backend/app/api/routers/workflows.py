from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.dependencies import DbSession
from app.models.workflow import ToolCall, WorkflowRun
from app.schemas.workflow import ToolCallResponse, WorkflowRunResponse

router = APIRouter(tags=["workflows"])


@router.get("/workflow-runs", response_model=list[WorkflowRunResponse])
async def list_workflow_runs(
    db: DbSession,
    meeting_id: str | None = None,
):
    """桌面端 Trace 列表，可按会议过滤工作流运行记录。"""
    statement = select(WorkflowRun)
    if meeting_id:
        statement = statement.where(WorkflowRun.meeting_id == meeting_id)
    statement = statement.order_by(WorkflowRun.created_at.desc())
    workflow_runs = (await db.execute(statement)).scalars().all()
    return [WorkflowRunResponse.from_model(workflow_run) for workflow_run in workflow_runs]


@router.get("/workflow-runs/{workflow_run_id}", response_model=WorkflowRunResponse)
async def get_workflow_run(
    workflow_run_id: str,
    db: DbSession,
):
    """桌面端轮询单个工作流运行状态。"""
    workflow_run = await db.get(WorkflowRun, workflow_run_id)
    if workflow_run is None:
        raise HTTPException(status_code=404, detail="workflow run not found")
    return WorkflowRunResponse.from_model(workflow_run)


@router.get(
    "/workflow-runs/{workflow_run_id}/tool-calls",
    response_model=list[ToolCallResponse],
)
async def list_workflow_tool_calls(
    workflow_run_id: str,
    db: DbSession,
):
    """查看某次工作流里发生的外部工具调用。"""
    workflow_run = await db.get(WorkflowRun, workflow_run_id)
    if workflow_run is None:
        raise HTTPException(status_code=404, detail="workflow run not found")

    statement = (
        select(ToolCall)
        .where(ToolCall.workflow_run_id == workflow_run_id)
        .order_by(ToolCall.created_at)
    )
    tool_calls = (await db.execute(statement)).scalars().all()
    return [ToolCallResponse.from_model(tool_call) for tool_call in tool_calls]
