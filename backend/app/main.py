from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import (
    action_items,
    analysis_drafts,
    debug,
    health,
    integrations,
    meetings,
    qa,
    reminders,
    workflows,
)
from app.core.config import config
from app.db.session import close_database


@asynccontextmanager
async def lifespan(_: FastAPI):
    """应用生命周期钩子，关闭时释放数据库连接池。"""
    yield
    await close_database()


app = FastAPI(title=config.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "tauri://localhost",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# main.py 只汇总 router；具体业务接口放在 app/api/routers 下按领域拆分。
app.include_router(health.router)
app.include_router(meetings.router)
app.include_router(qa.router)
app.include_router(analysis_drafts.router)
app.include_router(action_items.router)
app.include_router(reminders.router)
app.include_router(workflows.router)
app.include_router(integrations.router)
app.include_router(debug.router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=config.api_host,
        port=config.api_port,
        reload=False,
        log_level=config.api_log_level,
        access_log=True,
    )
