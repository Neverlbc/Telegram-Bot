"""Alembic 环境配置 — 支持 async 迁移."""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from bot.config import settings
from bot.models import Base

# 导入所有模型以确保 Alembic 能发现它们
from bot.models.user import User  # noqa: F401
from bot.models.product import Category, Product, ProductVariant  # noqa: F401
from bot.models.faq import FaqItem  # noqa: F401
from bot.models.order import WholesaleOrder, AftersaleQuery, LogisticsQuery  # noqa: F401
from bot.models.device import DeviceSerialQuery, DeviceTicket  # noqa: F401
from bot.models.ticket import SupportTicket, SupportMessage  # noqa: F401
from bot.models.analytics import AnalyticsEvent  # noqa: F401

# Alembic Config 对象
config = context.config

# 从 logging 配置文件加载日志设置
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 设置 target_metadata
target_metadata = Base.metadata

# 覆盖 sqlalchemy.url — 使用应用配置
config.set_main_option("sqlalchemy.url", settings.database_url)


def run_migrations_offline() -> None:
    """离线迁移模式（生成 SQL 脚本）."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """执行迁移."""
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """异步迁移模式."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """在线迁移模式（直接连接数据库）."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
