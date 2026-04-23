"""应用配置 — 使用 pydantic-settings 从 .env 加载."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """全局配置，从 .env / 环境变量加载."""

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Telegram Bot ──────────────────────────────────
    bot_token: str = Field(..., description="Telegram Bot Token")
    bot_mode: str = Field("polling", description="运行模式: polling / webhook")

    # ── MySQL ─────────────────────────────────────────
    mysql_host: str = Field("localhost")
    mysql_port: int = Field(3306)
    mysql_user: str = Field("bot_user")
    mysql_password: str = Field("")
    mysql_database: str = Field("telegram_bot")

    # ── Redis ─────────────────────────────────────────
    redis_host: str = Field("localhost")
    redis_port: int = Field(6379)
    redis_password: str = Field("")
    redis_db: int = Field(0)

    # ── Webhook ───────────────────────────────────────
    webhook_url: str = Field("")
    webhook_port: int = Field(8443)
    webhook_secret: str = Field("")

    # ── ERP 与 WMS (聚水潭 & 跨运宝) ───────────────────
    jushuitan_app_key: str = Field("")
    jushuitan_app_secret: str = Field("")
    jushuitan_api_url: str = Field("https://openapi.jushuitan.com")

    # Google Sheets 写入
    google_credentials_file: str = Field("google_credentials.json", description="Service Account JSON 路径")
    
    # 跨运宝配置
    kyb_app_id: str = Field("")
    kyb_app_secret: str = Field("")
    kyb_api_url: str = Field("https://open.imlb2c.com", description="跨运宝 API 地址")
    kyb_token: str = Field("")
    kyb_prefer_static_token: bool = Field(True)
    kyb_platform_customer_code: str = Field("", description="跨运宝平台客户编码 (stock_total_query 必填)")

    # ── 物流 API ──────────────────────────────────────
    cdek_client_id: str = Field("")
    cdek_client_secret: str = Field("")
    rupost_api_token: str = Field("")
    cainiao_app_key: str = Field("")
    cainiao_app_secret: str = Field("")

    # ── AI 自动回复 ────────────────────────────────────
    openai_api_key: str = Field("")
    openai_model: str = Field("gpt-4o-mini")
    ai_reply_max_count: int = Field(5, description="AI 回复最大触发次数，超过后转人工")
    ai_reply_ttl_days: int = Field(7, description="AI 回复计数 TTL (天)")

    # ── 管理员与客服 ───────────────────────────────────
    admin_ids: str = Field("", description="管理员 Telegram ID 列表，逗号分隔")
    support_group_id: int = Field(0, description="普通客服群组 Telegram ID")
    escalation_agent_id: int = Field(0, description="特定人工客服 Telegram ID")

    # ── 售中下单 — 分类转接 ────────────────────────────
    human_agent_username: str = Field("ABFOfficialGroup", description="统一人工客服 Telegram 用户名 (不带@)")
    aliexpress_store_url: str = Field(
        "https://www.aliexpress.com", description="动力工具速卖通店铺链接"
    )

    # ── 日志 ──────────────────────────────────────────
    log_level: str = Field("INFO")
    log_format: str = Field("json", description="日志格式: json / console")

    @property
    def admin_id_list(self) -> list[int]:
        """解析逗号分隔的管理员 ID 字符串为整数列表."""
        if not self.admin_ids.strip():
            return []
        return [int(x.strip()) for x in self.admin_ids.split(",") if x.strip()]

    # ── 派生属性 ──────────────────────────────────────

    @property
    def database_url(self) -> str:
        """SQLAlchemy async 连接字符串."""
        return (
            f"mysql+aiomysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
            "?charset=utf8mb4"
        )

    @property
    def database_url_sync(self) -> str:
        """同步连接字符串 (供 Alembic 迁移使用)."""
        return (
            f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
            "?charset=utf8mb4"
        )

    @property
    def redis_url(self) -> str:
        """Redis 连接字符串."""
        auth = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/{self.redis_db}"


# 全局单例
settings = Settings()  # type: ignore[call-arg]
