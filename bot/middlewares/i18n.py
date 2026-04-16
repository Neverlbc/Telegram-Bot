"""多语言 (i18n) 中间件."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, User as TgUser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models.user import Language, User

logger = logging.getLogger(__name__)

# 简单的翻译字典 — 后续会替换为 gettext
# 结构: { lang: { key: translation } }
_translations: dict[str, dict[str, str]] = {
    "zh": {},
    "en": {},
    "ru": {},
}


def _(text: str, lang: str = "zh") -> str:
    """翻译函数 — 简易版.

    优先使用翻译字典，未找到则返回原文。
    """
    return _translations.get(lang, {}).get(text, text)


# Telegram language_code → Language 映射
_TG_LANG_MAP: dict[str, Language] = {
    "zh": Language.ZH,
    "zh-hans": Language.ZH,
    "zh-hant": Language.ZH,
    "en": Language.EN,
    "ru": Language.RU,
}


def detect_language(tg_user: TgUser | None) -> Language:
    """根据 Telegram 用户信息推断语言偏好."""
    if tg_user and tg_user.language_code:
        code = tg_user.language_code.lower()
        if code in _TG_LANG_MAP:
            return _TG_LANG_MAP[code]
        # 尝试取前两位
        prefix = code[:2]
        if prefix in _TG_LANG_MAP:
            return _TG_LANG_MAP[prefix]
    return Language.ZH  # 默认中文


class I18nMiddleware(BaseMiddleware):
    """多语言中间件.

    从 DB 加载用户语言偏好，为 handler 注入以下参数：
    - ``lang``: 用户语言代码 (str)
    - ``i18n``: 翻译函数
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        lang = Language.ZH
        
        # 优先使用 UserMiddleware 注入的 user 对象
        current_user: User | None = data.get("current_user")
        
        if current_user:
            lang = current_user.language
        else:
            # 如果没有连上数据库/没挂载 current_user，尝试从 event 原始数据直接推断（fallback）
            tg_user: TgUser | None = None
            if isinstance(event, Message):
                tg_user = event.from_user
            elif isinstance(event, CallbackQuery):
                tg_user = event.from_user
            
            lang = detect_language(tg_user)

        data["lang"] = lang.value
        data["i18n"] = lambda text: _(text, lang.value)

        return await handler(event, data)
