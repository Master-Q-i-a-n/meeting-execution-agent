from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import get_logger
from app.models.analysis import ActionItem
from app.models.reminder import Reminder

logger = get_logger(__name__)

REMINDER_LOOKAHEAD_HOURS = 24
REMINDABLE_ACTION_ITEM_STATUSES = {"confirmed", "dispatched"}
FINISHED_ACTION_ITEM_STATUSES = {"done", "cancelled"}


@dataclass(frozen=True)
class ReminderScanResult:
    created_count: int
    skipped_count: int


def build_reminder_unique_key(
    *,
    reminder_type: str,
    action_item_id: str,
    due_at: datetime,
) -> str:
    """同一待办、同一截止时间、同一提醒类型只生成一条提醒。"""
    return f"{reminder_type}:{action_item_id}:{due_at.isoformat()}"


async def scan_due_action_item_reminders(
    db: AsyncSession,
    *,
    now: datetime | None = None,
    lookahead: timedelta = timedelta(hours=REMINDER_LOOKAHEAD_HOURS),
) -> ReminderScanResult:
    """扫描即将到期和已逾期的待办，并写入应用内提醒。

    这里只负责在当前事务中 add/flush，是否 commit 由 API 或 Celery task 决定。
    """
    scan_now = _normalize_datetime(now or datetime.now())
    window_end = scan_now + lookahead
    logger.info(
        "提醒扫描开始 now=%s window_end=%s",
        scan_now.isoformat(),
        window_end.isoformat(),
    )
    statement = (
        select(ActionItem)
        .where(ActionItem.due_at.is_not(None))
        .where(ActionItem.status.in_(REMINDABLE_ACTION_ITEM_STATUSES))
        .where(ActionItem.due_at <= window_end)
    )
    action_items = (await db.execute(statement)).scalars().all()
    logger.info("提醒扫描候选待办 action_item_count=%s", len(action_items))

    created_count = 0
    skipped_count = 0
    for action_item in action_items:
        if (
            action_item.status not in REMINDABLE_ACTION_ITEM_STATUSES
            or action_item.status in FINISHED_ACTION_ITEM_STATUSES
            or action_item.due_at is None
        ):
            continue

        due_at = _normalize_datetime(action_item.due_at)
        reminder_type = "overdue" if due_at < scan_now else "upcoming"
        unique_key = build_reminder_unique_key(
            reminder_type=reminder_type,
            action_item_id=action_item.id,
            due_at=due_at,
        )
        existing_reminder = await db.scalar(
            select(Reminder).where(Reminder.unique_key == unique_key)
        )
        if existing_reminder is not None:
            skipped_count += 1
            continue

        db.add(
            Reminder(
                action_item_id=action_item.id,
                reminder_type=reminder_type,
                status="unread",
                message=_build_reminder_message(action_item, reminder_type),
                due_at=due_at,
                triggered_at=scan_now,
                unique_key=unique_key,
            )
        )
        created_count += 1

    await db.flush()
    logger.info(
        "提醒扫描完成 created_count=%s skipped_count=%s",
        created_count,
        skipped_count,
    )
    return ReminderScanResult(created_count=created_count, skipped_count=skipped_count)


def _build_reminder_message(action_item: ActionItem, reminder_type: str) -> str:
    if reminder_type == "overdue":
        return f"待办已逾期：{action_item.title}"
    return f"待办即将到期：{action_item.title}"


def _normalize_datetime(value: datetime) -> datetime:
    """统一用 naive datetime 比较，避免 aware/naive 混用时报错。"""
    if value.tzinfo is None:
        return value
    return value.replace(tzinfo=None)
