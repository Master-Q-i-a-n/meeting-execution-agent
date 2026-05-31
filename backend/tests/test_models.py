import app.models  # noqa: F401
from app.db.base import Base


def test_core_tables_are_registered() -> None:
    """确认 SQLAlchemy 已经注册阶段一核心表。"""
    assert {
        "action_items",
        "audio_segments",
        "analysis_drafts",
        "decisions",
        "draft_confirmation_snapshots",
        "external_task_mappings",
        "meetings",
        "meeting_chunks",
        "reminders",
        "risk_items",
        "tool_calls",
        "unconfirmed_items",
        "workflow_runs",
    }.issubset(Base.metadata.tables.keys())
