from datetime import datetime
from typing import Annotated

from fastapi import Depends, File, Form, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session

# 所有 router 共用的数据库 session 依赖，避免每个文件重复写 Annotated。
DbSession = Annotated[AsyncSession, Depends(get_db_session)]

# 上传会议文件接口使用 multipart/form-data，这些类型别名集中放在这里。
MeetingUploadFile = Annotated[UploadFile, File()]
MeetingUploadTitle = Annotated[str | None, Form()]
MeetingOccurredAt = Annotated[datetime | None, Form()]
