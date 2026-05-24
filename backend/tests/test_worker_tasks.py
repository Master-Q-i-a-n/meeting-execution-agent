import asyncio

import pytest

from app.workers import tasks


def test_analysis_worker_disposes_database_after_graph(monkeypatch) -> None:
    """分析图成功结束后，worker 也要在当前 event loop 里释放数据库连接池。"""
    events: list[str] = []
    final_state = {
        "meeting_id": "meeting-1",
        "workflow_run_id": "workflow-1",
        "draft_id": "draft-1",
        "status": "draft",
    }

    async def fake_run_meeting_analysis_graph(*, meeting_id: str, workflow_run_id: str):
        assert meeting_id == "meeting-1"
        assert workflow_run_id == "workflow-1"
        events.append("graph")
        return final_state

    async def fake_close_database() -> None:
        events.append("close_database")

    monkeypatch.setattr(tasks, "run_meeting_analysis_graph", fake_run_meeting_analysis_graph)
    monkeypatch.setattr(tasks, "close_database", fake_close_database)

    result = asyncio.run(
        tasks._run_meeting_analysis_with_database_cleanup(
            meeting_id="meeting-1",
            workflow_run_id="workflow-1",
        )
    )

    assert result == final_state
    assert events == ["graph", "close_database"]


def test_analysis_worker_disposes_database_when_graph_fails(monkeypatch) -> None:
    """分析图报错时也要清连接池，避免下一次 Celery 任务复用旧异步连接。"""
    events: list[str] = []

    async def fake_run_meeting_analysis_graph(*, meeting_id: str, workflow_run_id: str):
        assert meeting_id == "meeting-1"
        assert workflow_run_id == "workflow-1"
        events.append("graph")
        raise RuntimeError("analysis failed")

    async def fake_close_database() -> None:
        events.append("close_database")

    monkeypatch.setattr(tasks, "run_meeting_analysis_graph", fake_run_meeting_analysis_graph)
    monkeypatch.setattr(tasks, "close_database", fake_close_database)

    with pytest.raises(RuntimeError, match="analysis failed"):
        asyncio.run(
            tasks._run_meeting_analysis_with_database_cleanup(
                meeting_id="meeting-1",
                workflow_run_id="workflow-1",
            )
        )

    assert events == ["graph", "close_database"]


def test_dispatch_worker_disposes_database_after_dispatch(monkeypatch) -> None:
    """外部派发 worker 也要在任务 loop 结束前释放异步数据库连接池。"""
    events: list[str] = []
    final_result = tasks.ExternalTaskDispatchResult(
        draft_id="draft-1",
        workflow_run_id="workflow-1",
        status="completed",
        succeeded_count=1,
        skipped_count=0,
        failed_count=0,
    )

    async def fake_run_external_task_dispatch(*, draft_id: str, workflow_run_id: str):
        assert draft_id == "draft-1"
        assert workflow_run_id == "workflow-1"
        events.append("dispatch")
        return final_result

    async def fake_close_database() -> None:
        events.append("close_database")

    monkeypatch.setattr(tasks, "run_external_task_dispatch", fake_run_external_task_dispatch)
    monkeypatch.setattr(tasks, "close_database", fake_close_database)

    result = asyncio.run(
        tasks._run_draft_dispatch_with_database_cleanup(
            draft_id="draft-1",
            workflow_run_id="workflow-1",
        )
    )

    assert result == final_result
    assert events == ["dispatch", "close_database"]
