"""用户静默注册与信息更新中间件."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, User as TgUser
from sqlalchemy.dialects.mysql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from bot.middlewares.i18n import detect_language
from bot.models.user import User

logger = logging.getLogger(__name__)


class UserMiddleware(BaseMiddleware):
    """自动注册或更新用户信息.

    从 Dispatcher 捕获的事件中提取 Telegram 用户数据，
    使用 MySQL 的 INSERT ... ON DUPLICATE KEY UPDATE 语法实现高效的 upsert，
    并把查询到的 `User` 模型实例注入到 handler 的 data["user"] 中。
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user: TgUser | None = None
        if isinstance(event, Message):
            tg_user = event.from_user
        elif isinstance(event, CallbackQuery):
            tg_user = event.from_user

        session: AsyncSession | None = data.get("session")

        # 仅当捕获到有效用户并开启了数据库会话时执行注册
        if tg_user and session:
            # 准备 upsert 语句
            stmt = insert(User).values(
                telegram_id=tg_user.id,
                username=tg_user.username,
                first_name=tg_user.first_name,
                last_name=tg_user.last_name,
                # 当用户不存在时，尝试推断初始语言
                language=detect_language(tg_user).value,
            )

            # 更新冲突时的策略：更新基本信息，但不覆盖 language（语言偏好由用户主动更改）
            update_dict = {
                "username": stmt.inserted.username,
                "first_name": stmt.inserted.first_name,
                "last_name": stmt.inserted.last_name,
            }
            
            stmt = stmt.on_duplicate_key_update(**update_dict)
            
            await session.execute(stmt)
            
            # 使用 flush 而非 commit：让外层 DbSessionMiddleware 统一决断
            await session.flush()

            # 将用户对象挂载到字典中传递给下层的 i18n/handlers
            # 因为 on_duplicate_key_update 不会返回更新后的完整对象实体，我们需要手工进行检索
            from sqlalchemy import select
            user_inst = await session.scalar(select(User).where(User.telegram_id == tg_user.id))
            data["current_user"] = user_inst
            
        return await handler(event, data)
