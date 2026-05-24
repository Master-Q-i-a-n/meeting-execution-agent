from fastapi import APIRouter, HTTPException

from app.core.config import config
from app.core.redis_client import check_redis_connection
from app.db.session import check_database_connection
from app.retrieval.qdrant_store import check_qdrant_connection

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check():
    """基础健康检查，不依赖外部服务。"""
    return {"status": "ok", "service": config.app_name}


@router.get("/health/db")
async def database_health_check():
    """检查 MySQL 连通性。"""
    await check_database_connection()
    return {"status": "ok", "database": config.mysql_database}


@router.get("/health/redis")
async def redis_health_check():
    """检查 Redis 连通性。"""
    try:
        await check_redis_connection()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Redis connection failed: {exc}") from exc
    return {"status": "ok", "redis": "connected"}


@router.get("/health/qdrant")
def qdrant_health_check():
    """检查 Qdrant 连通性。"""
    try:
        check_qdrant_connection()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Qdrant connection failed: {exc}") from exc
    return {"status": "ok", "qdrant": "connected"}
