from datetime import datetime

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.dependencies import DbSession
from app.core.logger import get_logger
from app.models.reminder import Reminder
from app.schemas.reminder import ReminderResponse

logger = get_logger(__name__)
router = APIRouter(tags=["reminders"])


@router.get("/reminders", response_model=list[ReminderResponse])
async def list_reminders(
    db: DbSession,
    status: str | None = "unread",
):
    """查看应用内提醒，默认只返回未读提醒。"""
    statement = select(Reminder)
    if status:
        statement = statement.where(Reminder.status == status)
    statement = statement.order_by(Reminder.triggered_at.desc())
    reminders = (await db.execute(statement)).scalars().all()
    return [ReminderResponse.from_model(reminder) for reminder in reminders]


@router.patch("/reminders/{reminder_id}/read", response_model=ReminderResponse)
async def mark_reminder_read(
    reminder_id: str,
    db: DbSession,
):
    """把一条应用内提醒标记为已读。"""
    reminder = await db.get(Reminder, reminder_id)
    if reminder is None:
        raise HTTPException(status_code=404, detail="reminder not found")

    reminder.status = "read"
    reminder.read_at = datetime.now()
    await db.commit()
    await db.refresh(reminder, attribute_names=["updated_at"])
    logger.info("提醒标记已读 reminder_id=%s", reminder_id)
    return ReminderResponse.from_model(reminder)
