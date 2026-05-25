from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app.api.routers.meetings as meetings_router
from app.db.session import get_db_session
from app.main import app
from app.models.meeting import Meeting
from app.models.workflow import WorkflowRun


class _FakeResult:
    def __init__(self, *, scalar=None, rows=None):
        self.scalar = scalar
        self.rows = rows or []

    def scalar_one_or_none(self):
        return self.scalar

    def scalars(self):
        return self

    def all(self):
        return self.rows


class _FakeDb:
    def __init__(self, *, execute_results=None, scalar_results=None):
        self.execute_results = list(execute_results or [])
        self.scalar_results = list(scalar_results or [])
        self.added_rows = []
        self.committed = False
        self.flushed = False

    async def execute(self, _statement):
        if self.execute_results:
            return self.execute_results.pop(0)
        return _FakeResult(rows=[])

    async def scalar(self, _statement):
        if self.scalar_results:
            return self.scalar_results.pop(0)
        return None

    def add(self, row):
        self.added_rows.append(row)

    async def flush(self):
        for row in self.added_rows:
            if isinstance(row, WorkflowRun) and row.id is None:
                row.id = "workflow-1"
        self.flushed = True

    async def commit(self):
        self.committed = True

    async def refresh(self, _row):
        return None


def _build_meeting(*, status: str = "uploaded") -> Meeting:
    now = datetime(2026, 5, 25, 10, 0, 0)
    return Meeting(
        id="meeting-1",
        title="Analyze guard test",
        source_type="markdown",
        status=status,
        raw_content="meeting content",
        metadata_json={},
        created_at=now,
        updated_at=now,
    )


def _override_db(fake_db: _FakeDb):
    async def _dependency():
        yield fake_db

    app.dependency_overrides[get_db_session] = _dependency


def _clear_overrides() -> None:
    app.dependency_overrides.clear()


@pytest.mark.parametrize("draft_status", ["confirmed", "dispatching", "completed", "failed"])
def test_analyze_meeting_blocks_locked_draft_statuses(
    client: TestClient,
    draft_status: str,
) -> None:
    fake_db = _FakeDb(
        execute_results=[_FakeResult(scalar=_build_meeting(status=draft_status))],
        scalar_results=[f"{draft_status}-draft"],
    )
    _override_db(fake_db)

    try:
        response = client.post("/meetings/meeting-1/analyze")
    finally:
        _clear_overrides()

    assert response.status_code == 409
    assert (
        response.json()["detail"]
        == "meeting already has confirmed or dispatched draft; re-analysis is disabled"
    )
    assert fake_db.added_rows == []
    assert fake_db.committed is False


@pytest.mark.parametrize("workflow_status", ["pending", "running", "analyzing", "dispatching"])
def test_analyze_meeting_blocks_active_workflows(
    client: TestClient,
    workflow_status: str,
) -> None:
    fake_db = _FakeDb(
        execute_results=[_FakeResult(scalar=_build_meeting())],
        scalar_results=[None, f"{workflow_status}-workflow"],
    )
    _override_db(fake_db)

    try:
        response = client.post("/meetings/meeting-1/analyze")
    finally:
        _clear_overrides()

    assert response.status_code == 409
    assert response.json()["detail"] == "meeting has active workflow, wait until it finishes"
    assert fake_db.added_rows == []
    assert fake_db.committed is False


@pytest.mark.parametrize("meeting_status", ["uploaded", "draft", "needs_input"])
def test_analyze_meeting_allows_unlocked_meeting_statuses(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    meeting_status: str,
) -> None:
    meeting = _build_meeting(status=meeting_status)
    fake_db = _FakeDb(
        execute_results=[
            _FakeResult(scalar=meeting),
            _FakeResult(rows=[]),
        ],
        scalar_results=[None, None],
    )
    _override_db(fake_db)
    monkeypatch.setattr(meetings_router, "check_redis_connection_sync", lambda: None)
    monkeypatch.setattr(
        meetings_router,
        "analyze_meeting_task",
        SimpleNamespace(delay=lambda *_args: SimpleNamespace(id="task-1", status="PENDING")),
    )

    try:
        response = client.post("/meetings/meeting-1/analyze")
    finally:
        _clear_overrides()

    assert response.status_code == 200
    assert response.json()["meeting_id"] == "meeting-1"
    assert response.json()["task_id"] == "task-1"
    assert meeting.status == "analyzing"
    assert fake_db.committed is True
    assert any(isinstance(row, WorkflowRun) for row in fake_db.added_rows)
