from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.models.workflow import ToolCall, WorkflowRun


class ToolCallResponse(BaseModel):
    """桌面端 Trace 页展示单次外部工具调用。"""

    id: str
    workflow_run_id: str | None
    tool_name: str
    idempotency_key: str | None
    status: str
    request_json: dict[str, Any] | None
    response_json: dict[str, Any] | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, tool_call: ToolCall) -> "ToolCallResponse":
        return cls(
            id=tool_call.id,
            workflow_run_id=tool_call.workflow_run_id,
            tool_name=tool_call.tool_name,
            idempotency_key=tool_call.idempotency_key,
            status=tool_call.status,
            request_json=tool_call.request_json,
            response_json=tool_call.response_json,
            error_message=tool_call.error_message,
            created_at=tool_call.created_at,
            updated_at=tool_call.updated_at,
        )


class WorkflowRunResponse(BaseModel):
    """桌面端轮询长任务进度时使用的工作流快照。"""

    id: str
    meeting_id: str | None
    workflow_type: str
    current_node: str | None
    status: str
    payload_json: dict[str, Any] | None
    error_message: str | None
    retry_count: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, workflow_run: WorkflowRun) -> "WorkflowRunResponse":
        return cls(
            id=workflow_run.id,
            meeting_id=workflow_run.meeting_id,
            workflow_type=workflow_run.workflow_type,
            current_node=workflow_run.current_node,
            status=workflow_run.status,
            payload_json=workflow_run.payload_json,
            error_message=workflow_run.error_message,
            retry_count=workflow_run.retry_count,
            created_at=workflow_run.created_at,
            updated_at=workflow_run.updated_at,
        )
