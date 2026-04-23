"""应用初始化 — Bot、Dispatcher、中间件注册、路由挂载."""

from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from redis.asyncio import Redis

from bot.config import settings
from bot.handlers import (
    inventory,
    menu,
    service_center,
    vip,
    settings as settings_handler,
    start,
)
from bot.middlewares.i18n import I18nMiddleware
from bot.services.notification import notification_service

logger = logging.getLogger(__name__)


def create_redis() -> Redis | None:  # type: ignore[type-arg]
    """创建 Redis 客户端. 连接失败返回 None."""
    if not settings.redis_host:
        return None
    return Redis.from_url(
        settings.redis_url,
        decode_responses=True,
    )


def create_bot() -> Bot:
    """创建 Bot 实例."""
    return Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_dispatcher(redis: Redis | None = None) -> Dispatcher:  # type: ignore[type-arg]
    """创建 Dispatcher 并注册中间件和路由."""
    if redis:
        try:
            from aiogram.fsm.storage.redis import RedisStorage
            storage = RedisStorage(redis)
            logger.info("Using Redis FSM storage")
        except Exception:
            storage = MemoryStorage()
            logger.warning("Redis unavailable, using MemoryStorage for FSM")
    else:
        storage = MemoryStorage()
        logger.info("Using MemoryStorage for FSM (Redis not configured)")

    dp = Dispatcher(storage=storage)

    # ── 注册中间件 ────────────────────────────────────
    if redis:
        from bot.middlewares.throttle import ThrottleMiddleware
        dp.message.middleware(ThrottleMiddleware(redis))
        dp.callback_query.middleware(ThrottleMiddleware(redis))
        logger.info("Throttle middleware enabled")

    if settings.mysql_password and settings.mysql_password != "your_password_here":
        from bot.middlewares.db import DbSessionMiddleware
        from bot.middlewares.user import UserMiddleware
        dp.message.middleware(DbSessionMiddleware())
        dp.callback_query.middleware(DbSessionMiddleware())
        dp.message.middleware(UserMiddleware())
        dp.callback_query.middleware(UserMiddleware())
        logger.info("DB & User middleware enabled")
    else:
        logger.warning("DB & User middleware SKIPPED (mysql_password not configured)")

    dp.message.middleware(I18nMiddleware())
    dp.callback_query.middleware(I18nMiddleware())

    # ── 注册路由（顺序很重要：vip.py 的自由文本 handler 必须最后注册）──
    dp.include_router(start.router)
    dp.include_router(menu.router)
    dp.include_router(inventory.router)
    dp.include_router(service_center.router)
    dp.include_router(settings_handler.router)
    dp.include_router(vip.router)   # 最后注册，避免捕获其他 handler 的文本输入

    # ── 全局错误处理 ─────────────────────────────────
    @dp.error()
    async def global_error_handler(event, exception) -> bool:  # type: ignore[no-untyped-def]
        logger.exception("Unhandled error: %s", exception)
        return True

    return dp


async def on_startup(bot: Bot) -> None:
    """应用启动回调."""
    notification_service.set_bot(bot)

    from aiogram.types import BotCommand
    commands = [
        BotCommand(command="start", description="启动机器人"),
        BotCommand(command="menu", description="返回主菜单"),
        BotCommand(command="help", description="帮助信息"),
        BotCommand(command="lang", description="切换语言"),
        BotCommand(command="cancel", description="取消当前操作"),
    ]
    await bot.set_my_commands(commands)
    logger.info("Bot started, commands registered.")


async def on_shutdown(bot: Bot) -> None:
    """应用关停回调."""
    logger.info("Bot shutting down...")
