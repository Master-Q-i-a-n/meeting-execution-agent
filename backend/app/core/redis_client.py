import redis.asyncio as redis
from redis import Redis

from app.core.config import config


async def check_redis_connection() -> bool:
    """检查 Redis 是否可用。

    Redis 在当前阶段主要承担两个角色：
    1. Celery 的 broker，用来接收 FastAPI 投递的后台任务。
    2. Celery 的 result backend，用来保存任务执行结果。
    """
    client = redis.Redis.from_url(
        config.redis_url,
        decode_responses=True,
        socket_connect_timeout=1,
        socket_timeout=1,
    )
    try:
        return bool(await client.ping())
    finally:
        await client.aclose()


def check_redis_connection_sync() -> bool:
    """同步版 Redis 检查。

    Celery 投递接口是普通同步接口，所以先用这个快速检查 Redis。
    如果 Redis 没启动，就直接返回 503，避免 Celery 发布任务时长时间等待。
    """
    client = Redis.from_url(
        config.redis_url,
        decode_responses=True,
        socket_connect_timeout=1,
        socket_timeout=1,
    )
    try:
        return bool(client.ping())
    finally:
        client.close()
