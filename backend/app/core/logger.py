import logging
from datetime import datetime
from pathlib import Path

# backend 目录：后续把绝对路径转换成 app.services.xxx.py 这种模块路径时要用。
BACKEND_DIR = Path(__file__).resolve().parents[2]
LOG_ROOT = BACKEND_DIR / "logs"
LOG_ROOT.mkdir(parents=True, exist_ok=True)


class AgentLogFormatter(logging.Formatter):
    """把日志格式统一成固定 Agent 名称 + Python 模块路径。"""

    def format(self, record: logging.LogRecord) -> str:
        record.agent_location = format_agent_location(record)
        return super().format(record)


def format_agent_location(record: logging.LogRecord) -> str:
    """把 record.pathname 转成 app.services.xxx.py:12 这种显示形式。"""
    path = Path(record.pathname)
    try:
        relative_path = path.resolve().relative_to(BACKEND_DIR)
    except ValueError:
        # 如果是第三方库或临时文件，退回文件名，避免日志格式化失败。
        relative_path = Path(path.name)
    module_path = ".".join(relative_path.parts)
    return f"{module_path}:{record.lineno}"


def get_backend_log_file() -> Path:
    """当天统一日志文件路径。"""
    return LOG_ROOT / f"backend_{datetime.now().strftime('%Y%m%d')}.log"


DEFAULT_LOG_FORMAT = AgentLogFormatter(
    "%(asctime)s - Agent - %(levelname)s - %(agent_location)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def get_logger(
    name: str = "backend",
    file_level: int = logging.DEBUG,
    log_file: str | Path | None = None,
) -> logging.Logger:
    """获取项目业务 logger。

    v1 只写文件，不输出控制台；控制台上的 uvicorn/Celery 框架日志不在这里接管。
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    for handler in list(logger.handlers):
        if getattr(handler, "_agent_file_handler", False):
            return logger
        # 旧版 logger 可能已经加过控制台 handler；新版业务日志统一只保留文件输出。
        handler.close()
        logger.removeHandler(handler)

    file_path = Path(log_file) if log_file is not None else get_backend_log_file()
    file_path.parent.mkdir(parents=True, exist_ok=True)

    file_handler = logging.FileHandler(file_path, encoding="utf-8")
    file_handler._agent_file_handler = True
    file_handler.setLevel(file_level)
    file_handler.setFormatter(DEFAULT_LOG_FORMAT)
    logger.addHandler(file_handler)

    return logger


logger = get_logger()


if __name__ == "__main__":
    logger.info("信息日志")
    logger.error("错误日志")
    logger.warning("警告日志")
    logger.debug("调试日志")
