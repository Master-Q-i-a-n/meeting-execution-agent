import logging
from pathlib import Path

from app.core import logger as logger_module
from app.core.logger import AgentLogFormatter, format_agent_location, get_logger


def _close_test_logger(logger: logging.Logger) -> None:
    """测试里主动清理 handler，避免影响后续用例。"""
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)


def test_format_agent_location_uses_python_module_path() -> None:
    """后端文件路径要显示成 app.services.xxx.py:行号。"""
    record = logging.LogRecord(
        name="any.logger.name",
        level=logging.INFO,
        pathname=str(
            logger_module.BACKEND_DIR / "app" / "services" / "analysis_drafts.py"
        ),
        lineno=12,
        msg="message",
        args=(),
        exc_info=None,
    )

    assert format_agent_location(record) == "app.services.analysis_drafts.py:12"


def test_agent_formatter_uses_fixed_agent_name() -> None:
    """日志中间的名称固定为 Agent，不跟随 logger name 变化。"""
    record = logging.LogRecord(
        name="app.services.analysis_drafts",
        level=logging.INFO,
        pathname=str(
            logger_module.BACKEND_DIR / "app" / "services" / "analysis_drafts.py"
        ),
        lineno=12,
        msg="message",
        args=(),
        exc_info=None,
    )
    formatter = AgentLogFormatter(
        "%(asctime)s - Agent - %(levelname)s - %(agent_location)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    output = formatter.format(record)

    assert " - Agent - INFO - app.services.analysis_drafts.py:12 - message" in output
    assert "app.services.analysis_drafts - INFO" not in output


def test_get_logger_writes_only_file_handler(tmp_path: Path) -> None:
    """业务 logger 只写文件，不额外添加控制台 StreamHandler。"""
    log_file = tmp_path / "backend_test.log"
    test_logger = get_logger("test.logger.file_only", log_file=log_file)

    try:
        assert test_logger.propagate is False
        assert len(test_logger.handlers) == 1
        assert isinstance(test_logger.handlers[0], logging.FileHandler)
        assert not any(
            type(handler) is logging.StreamHandler for handler in test_logger.handlers
        )

        test_logger.info("hello")
        for handler in test_logger.handlers:
            handler.flush()

        log_content = log_file.read_text(encoding="utf-8")
        assert " - Agent - INFO - " in log_content
        assert " - hello" in log_content
    finally:
        _close_test_logger(test_logger)


def test_get_logger_does_not_duplicate_handlers(tmp_path: Path) -> None:
    """重复获取同名 logger 时不能反复追加 FileHandler。"""
    log_file = tmp_path / "backend_test.log"
    first_logger = get_logger("test.logger.no_duplicate", log_file=log_file)
    second_logger = get_logger("test.logger.no_duplicate", log_file=log_file)

    try:
        assert first_logger is second_logger
        assert len(second_logger.handlers) == 1
    finally:
        _close_test_logger(second_logger)
