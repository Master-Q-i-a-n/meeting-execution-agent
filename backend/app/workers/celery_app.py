from celery import Celery

from app.core.config import config

# Celery 是独立于 FastAPI 的后台任务进程。
# FastAPI 只负责把任务投递到 Redis，真正执行任务的是 celery worker。
celery_app = Celery(
    "meeting_execution_agent",
    broker=config.celery_broker_url,
    backend=config.celery_result_backend,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    accept_content=["json"],
    broker_connection_timeout=3,
    broker_transport_options={
        "socket_connect_timeout": 3,
        "socket_timeout": 3,
    },
    result_serializer="json",
    result_backend_transport_options={
        "socket_connect_timeout": 3,
        "socket_timeout": 3,
    },
    task_serializer="json",
    task_publish_retry=False,
    task_track_started=True,
    timezone="Asia/Shanghai",
    enable_utc=False,
    beat_schedule={
        "scan-due-action-items-every-10-minutes": {
            "task": "reminders.scan_due_action_items",
            "schedule": 600.0,
        },
    },
)

# 让命令 `celery -A app.workers.celery_app worker ...` 能自动找到 Celery 实例。
app = celery_app
