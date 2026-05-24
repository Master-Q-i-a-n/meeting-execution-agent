from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from app.models.analysis import ActionItem
from app.services.reminders import (
    build_reminder_unique_key,
    scan_due_action_item_reminders,
)


class FakeReminderSession:
    def __init__(self, action_items: list[ActionItem], existing_keys: set[str] | None = None) -> None:
        self.action_items = action_items
        self.existing_keys = existing_keys or set()
        self.added = []
        self.flushed = False

    async def execute(self, _statement):
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: self.action_items))

    async def scalar(self, statement):
        text = str(statement.compile(compile_kwargs={"literal_binds": True}))
        for key in self.existing_keys:
            if key in text:
                return object()
        return None

    def add(self, reminder) -> None:
        self.added.append(reminder)

    async def flush(self) -> None:
        self.flushed = True


@pytest.mark.asyncio
async def test_scan_due_action_item_reminders_creates_upcoming_and_overdue() -> None:
    now = datetime(2026, 5, 23, 10, 0)
    session = FakeReminderSession(
        [
            ActionItem(
                id="action-upcoming",
                title="完成联调",
                status="confirmed",
                due_at=now + timedelta(hours=2),
            ),
            ActionItem(
                id="action-overdue",
                title="补齐文档",
                status="dispatched",
                due_at=now - timedelta(hours=1),
            ),
            ActionItem(
                id="action-draft",
                title="草稿不提醒",
                status="draft",
                due_at=now + timedelta(hours=1),
            ),
            ActionItem(
                id="action-done",
                title="完成不提醒",
                status="done",
                due_at=now - timedelta(hours=1),
            ),
        ]
    )

    result = await scan_due_action_item_reminders(session, now=now)  # type: ignore[arg-type]

    assert result.created_count == 2
    assert [reminder.reminder_type for reminder in session.added] == ["upcoming", "overdue"]
    assert session.flushed is True


@pytest.mark.asyncio
async def test_scan_due_action_item_reminders_skips_existing_unique_key() -> None:
    now = datetime(2026, 5, 23, 10, 0)
    due_at = now + timedelta(hours=2)
    existing_key = build_reminder_unique_key(
        reminder_type="upcoming",
        action_item_id="action-1",
        due_at=due_at,
    )
    session = FakeReminderSession(
        [
            ActionItem(
                id="action-1",
                title="完成联调",
                status="confirmed",
                due_at=due_at,
            )
        ],
        existing_keys={existing_key},
    )

    result = await scan_due_action_item_reminders(session, now=now)  # type: ignore[arg-type]

    assert result.created_count == 0
    assert result.skipped_count == 1
    assert session.added == []
