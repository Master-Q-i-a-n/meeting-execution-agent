from datetime import datetime

from fastapi.testclient import TestClient

from app.db.session import get_db_session
from app.main import app
from app.models.meeting import Meeting
from app.models.workflow import ToolCall, WorkflowRun


class _FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return self

    def all(self):
        return self.rows


class _FakeDb:
    def __init__(self, *, execute_rows=None, get_rows=None):
        self.execute_rows = execute_rows or []
        self.get_rows = get_rows or {}

    async def execute(self, _statement):
        return _FakeResult(self.execute_rows)

    async def get(self, model, row_id):
        return self.get_rows.get((model, row_id))


def _override_db(fake_db: _FakeDb):
    async def _dependency():
        yield fake_db

    app.dependency_overrides[get_db_session] = _dependency


def _clear_overrides() -> None:
    app.dependency_overrides.clear()


def test_list_meetings_returns_desktop_summary(client: TestClient) -> None:
    now = datetime(2026, 5, 23, 20, 0, 0)
    meeting = Meeting(
        id="meeting-1",
        title="桌面端测试会议",
        source_type="markdown",
        status="draft",
        raw_content="第一段会议内容\n第二段会议内容",
        metadata_json={"source": "test"},
        occurred_at=now,
        created_at=now,
        updated_at=now,
    )
    _override_db(_FakeDb(execute_rows=[meeting]))

    try:
        response = client.get("/meetings")
    finally:
        _clear_overrides()

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["id"] == "meeting-1"
    assert payload[0]["content_length"] == len(meeting.raw_content)
    assert payload[0]["content_preview"] == "第一段会议内容 第二段会议内容"


def test_get_workflow_run_returns_trace_snapshot(client: TestClient) -> None:
    now = datetime(2026, 5, 23, 20, 0, 0)
    workflow_run = WorkflowRun(
        id="workflow-1",
        meeting_id="meeting-1",
        workflow_type="meeting_analysis",
        current_node="index_semantic_documents",
        status="running",
        payload_json={"index_status": "pending"},
        error_message=None,
        retry_count=0,
        created_at=now,
        updated_at=now,
    )
    _override_db(_FakeDb(get_rows={(WorkflowRun, "workflow-1"): workflow_run}))

    try:
        response = client.get("/workflow-runs/workflow-1")
    finally:
        _clear_overrides()

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "workflow-1"
    assert payload["current_node"] == "index_semantic_documents"
    assert payload["payload_json"] == {"index_status": "pending"}


def test_list_workflow_tool_calls_returns_audit_rows(client: TestClient) -> None:
    now = datetime(2026, 5, 23, 20, 0, 0)
    workflow_run = WorkflowRun(
        id="workflow-1",
        meeting_id="meeting-1",
        workflow_type="external_task_dispatch",
        current_node="finish",
        status="completed",
        payload_json={},
        error_message=None,
        retry_count=0,
        created_at=now,
        updated_at=now,
    )
    tool_call = ToolCall(
        id="tool-call-1",
        workflow_run_id="workflow-1",
        tool_name="linear.create_task",
        idempotency_key="linear:dispatch:draft:item",
        status="succeeded",
        request_json={"title": "测试待办"},
        response_json={"data": {"issueCreate": {"success": True}}},
        error_message=None,
        created_at=now,
        updated_at=now,
    )
    _override_db(
        _FakeDb(
            execute_rows=[tool_call],
            get_rows={(WorkflowRun, "workflow-1"): workflow_run},
        )
    )

    try:
        response = client.get("/workflow-runs/workflow-1/tool-calls")
    finally:
        _clear_overrides()

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["id"] == "tool-call-1"
    assert payload[0]["tool_name"] == "linear.create_task"
    assert payload[0]["status"] == "succeeded"
