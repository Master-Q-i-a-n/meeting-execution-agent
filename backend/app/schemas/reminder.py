from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.models.reminder import Reminder


class ReminderResponse(BaseModel):
    """应用内提醒响应。"""

    # 提醒记录 ID。
    id: str
    # 关联的本地待办 ID。
    action_item_id: str
    # 提醒类型：upcoming 或 overdue。
    reminder_type: str
    # 提醒状态：unread 或 read。
    status: str
    # 展示给用户看的提醒文案。
    message: str
    # 待办截止时间快照。
    due_at: datetime
    # 提醒生成时间。
    triggered_at: datetime
    # 用户读取时间，未读时为空。
    read_at: datetime | None
    # 错误摘要，当前应用内提醒通常为空。
    error_message: str | None
    # 记录创建时间。
    created_at: datetime
    # 记录更新时间。
    updated_at: datetime

    @classmethod
    def from_model(cls, reminder: Reminder) -> "ReminderResponse":
        return cls(
            id=reminder.id,
            action_item_id=reminder.action_item_id,
            reminder_type=reminder.reminder_type,
            status=reminder.status,
            message=reminder.message,
            due_at=reminder.due_at,
            triggered_at=reminder.triggered_at,
            read_at=reminder.read_at,
            error_message=reminder.error_message,
            created_at=reminder.created_at,
            updated_at=reminder.updated_at,
        )


class ReminderScanResponse(BaseModel):
    """提醒扫描结果响应。"""

    # 本次扫描新生成的提醒数量。
    created_count: int
    # 本次扫描跳过的重复提醒数量。
    skipped_count: int


class ActionItemStatusUpdateRequest(BaseModel):
    """手动更新本地待办状态。"""

    # v1 只允许用户手动标记完成或取消。
    status: Literal["done", "cancelled"]
