"""Bot 启动入口 — 支持 Polling 和 Webhook 两种模式."""

from __future__ import annotations

import argparse
import asyncio
import logging

from bot.app import create_bot, create_dispatcher, create_redis, on_shutdown, on_startup
from bot.config import settings
from bot.logging_config import setup_logging

logger = logging.getLogger(__name__)


async def run_polling() -> None:
    """以 Polling 模式启动 Bot（开发环境）."""
    redis = None
    try:
        redis = create_redis()
        if redis:
            await redis.ping()
            logger.info("Redis connected successfully")
    except Exception as e:
        logger.warning("Redis connection failed (%s), running without Redis", e)
        redis = None

    bot = create_bot()
    dp = create_dispatcher(redis)

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    logger.info("Starting bot in POLLING mode...")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        if redis:
            await redis.aclose()
        await bot.session.close()


async def run_webhook() -> None:
    """以 Webhook 模式启动 Bot（生产环境）."""
    from aiohttp import web

    redis = create_redis()
    bot = create_bot()
    dp = create_dispatcher(redis)

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # 设置 Webhook
    webhook_url = f"{settings.webhook_url}/webhook"
    await bot.set_webhook(
        url=webhook_url,
        secret_token=settings.webhook_secret,
        allowed_updates=dp.resolve_used_update_types(),
    )

    # aiohttp web app
    app = web.Application()

    from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

    handler = SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=settings.webhook_secret)
    handler.register(app, path="/webhook")
    setup_application(app, dp, bot=bot)

    logger.info("Starting bot in WEBHOOK mode at %s:%s", "0.0.0.0", settings.webhook_port)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=settings.webhook_port)

    try:
        await site.start()
        # 保持运行
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()
        await bot.delete_webhook()
        await redis.aclose()
        await bot.session.close()


def main() -> None:
    """解析命令行参数并启动 Bot."""
    parser = argparse.ArgumentParser(description="Telegram Bot")
    parser.add_argument(
        "--webhook",
        action="store_true",
        default=False,
        help="以 Webhook 模式启动 (默认: Polling)",
    )
    args = parser.parse_args()

    # 初始化日志
    setup_logging(settings.log_level, settings.log_format)

    # 根据参数或配置决定运行模式
    use_webhook = args.webhook or settings.bot_mode == "webhook"

    if use_webhook:
        asyncio.run(run_webhook())
    else:
        asyncio.run(run_polling())


if __name__ == "__main__":
    main()
