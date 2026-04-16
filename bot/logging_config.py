"""结构化日志配置 — 基于 structlog."""

from __future__ import annotations

import logging
import sys

import structlog


def setup_logging(log_level: str = "INFO", log_format: str = "json") -> None:
    """初始化 structlog + stdlib logging.

    Args:
        log_level: 日志级别 (DEBUG / INFO / WARNING / ERROR).
        log_format: 输出格式 ("json" 或 "console").
    """
    level = getattr(logging, log_level.upper(), logging.INFO)

    # 共享的处理器链
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if log_format == "console":
        renderer: structlog.types.Processor = structlog.dev.ConsoleRenderer(colors=True)
    else:
        renderer = structlog.processors.JSONRenderer(ensure_ascii=False)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)

    # 降低第三方库日志级别
    for name in ("aiogram", "aiohttp", "sqlalchemy", "alembic"):
        logging.getLogger(name).setLevel(max(level, logging.WARNING))
