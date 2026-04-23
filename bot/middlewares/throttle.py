"""频率限制中间件 — 基于 Redis INCR + EXPIRE."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from redis.asyncio import Redis

logger = logging.getLogger(__name__)


class ThrottleMiddleware(BaseMiddleware):
    """全局频率限制：同一用户每秒最多 N 次请求.

    超过限制时静默忽略请求。
    """

    def __init__(self, redis: Redis, rate_limit: int = 2, window: int = 1) -> None:  # type: ignore[type-arg]
        """初始化.

        Args:
            redis: Redis 客户端实例.
            rate_limit: 窗口内最大请求数.
            window: 时间窗口（秒）.
        """
        self.redis = redis
        self.rate_limit = rate_limit
        self.window = window

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        # 提取用户 ID
        user_id: int | None = None
        if isinstance(event, Message) and event.from_user:
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery) and event.from_user:
            user_id = event.from_user.id

        if user_id is None:
            return await handler(event, data)

        key = f"throttle:{user_id}"
        current = await self.redis.incr(key)

        if current == 1:
            await self.redis.expire(key, self.window)

        if current > self.rate_limit:
            logger.debug("Throttled user %s (count=%s)", user_id, current)
            return None  # 静默忽略

        return await handler(event, data)
