"""配置模块单元测试."""

from __future__ import annotations

import os
from unittest.mock import patch


def test_parse_admin_ids_from_string() -> None:
    """测试从逗号分隔字符串解析管理员 ID 列表."""
    from bot.config import Settings

    with patch.dict(os.environ, {"BOT_TOKEN": "test:token", "ADMIN_IDS": "123,456,789"}):
        s = Settings()  # type: ignore[call-arg]
        assert s.admin_id_list == [123, 456, 789]


def test_parse_admin_ids_empty() -> None:
    """测试空管理员 ID."""
    from bot.config import Settings

    with patch.dict(os.environ, {"BOT_TOKEN": "test:token", "ADMIN_IDS": ""}):
        s = Settings()  # type: ignore[call-arg]
        assert s.admin_id_list == []


def test_database_url() -> None:
    """测试数据库 URL 生成."""
    from bot.config import Settings

    with patch.dict(os.environ, {
        "BOT_TOKEN": "test:token",
        "MYSQL_USER": "user",
        "MYSQL_PASSWORD": "pass",
        "MYSQL_HOST": "db",
        "MYSQL_PORT": "3306",
        "MYSQL_DATABASE": "testdb",
    }):
        s = Settings()  # type: ignore[call-arg]
        assert "mysql+aiomysql://user:pass@db:3306/testdb" in s.database_url
        assert "charset=utf8mb4" in s.database_url


def test_redis_url() -> None:
    """测试 Redis URL 生成."""
    from bot.config import Settings

    with patch.dict(os.environ, {
        "BOT_TOKEN": "test:token",
        "REDIS_HOST": "cache",
        "REDIS_PORT": "6380",
        "REDIS_DB": "1",
    }):
        s = Settings()  # type: ignore[call-arg]
        assert "redis://cache:6380/1" in s.redis_url
