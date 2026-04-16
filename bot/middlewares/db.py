"""数据库会话注入中间件."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from bot.models import async_session


class DbSessionMiddleware(BaseMiddleware):
    """为每个请求注入一个数据库会话.

    Handler 通过参数 ``session`` 获取 ``AsyncSession``。
    请求结束后自动提交或回滚。
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with async_session() as session:
            data["session"] = session
            try:
                result = await handler(event, data)
                await session.commit()
                return result
            except Exception:
                await session.rollback()
                raise
