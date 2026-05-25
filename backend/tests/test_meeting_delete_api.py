from datetime import datetime

from fastapi.testclient import TestClient

import app.api.routers.meetings as meetings_router
from app.db.session import get_db_session
from app.main import app
from app.models.meeting import Meeting


class _FakeDb:
    def __init__(self, *, meeting: Meeting | None = None, active_workflow_id: str | None = None):
        self.meeting = meeting
        self.active_workflow_id = active_workflow_id
        self.deleted_rows = []
        self.committed = False
        self.rolled_back = False

    async def get(self, model, row_id):
        if model is Meeting and self.meeting is not None and self.meeting.id == row_id:
            return self.meeting
        return None

    async def scalar(self, _statement):
        return self.active_workflow_id

    async def delete(self, row):
        self.deleted_rows.append(row)

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


def _build_meeting() -> Meeting:
    now = datetime(2026, 5, 24, 20, 0, 0)
    return Meeting(
        id="meeting-1",
        title="Delete API test",
        source_type="markdown",
        status="draft",
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


def test_delete_meeting_returns_404_when_missing(client: TestClient) -> None:
    _override_db(_FakeDb())

    try:
        response = client.delete("/meetings/missing")
    finally:
        _clear_overrides()

    assert response.status_code == 404
    assert response.json()["detail"] == "meeting not found"


def test_delete_meeting_blocks_active_workflow(client: TestClient, monkeypatch) -> None:
    fake_db = _FakeDb(meeting=_build_meeting(), active_workflow_id="workflow-1")
    _override_db(fake_db)
    monkeypatch.setattr(
        meetings_router,
        "delete_meeting_points",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("should not delete qdrant")),
    )

    try:
        response = client.delete("/meetings/meeting-1")
    finally:
        _clear_overrides()

    assert response.status_code == 409
    assert fake_db.deleted_rows == []
    assert fake_db.committed is False


def test_delete_meeting_keeps_mysql_when_qdrant_cleanup_fails(
    client: TestClient,
    monkeypatch,
) -> None:
    fake_db = _FakeDb(meeting=_build_meeting())
    _override_db(fake_db)

    def _fail_qdrant(**_kwargs):
        raise RuntimeError("qdrant unavailable")

    monkeypatch.setattr(meetings_router, "delete_meeting_points", _fail_qdrant)

    try:
        response = client.delete("/meetings/meeting-1")
    finally:
        _clear_overrides()

    assert response.status_code == 503
    assert "qdrant cleanup failed" in response.json()["detail"]
    assert fake_db.deleted_rows == []
    assert fake_db.committed is False


def test_delete_meeting_removes_mysql_after_qdrant_cleanup(
    client: TestClient,
    monkeypatch,
) -> None:
    meeting = _build_meeting()
    fake_db = _FakeDb(meeting=meeting)
    _override_db(fake_db)
    monkeypatch.setattr(
        meetings_router,
        "delete_meeting_points",
        lambda **kwargs: {"status": "ok", "meeting_id": kwargs["meeting_id"]},
    )

    try:
        response = client.delete("/meetings/meeting-1")
    finally:
        _clear_overrides()

    assert response.status_code == 200
    assert response.json() == {
        "meeting_id": "meeting-1",
        "status": "deleted",
        "qdrant": {"status": "ok", "meeting_id": "meeting-1"},
    }
    assert fake_db.deleted_rows == [meeting]
    assert fake_db.committed is True
