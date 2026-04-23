"""/start 命令 — 新用户欢迎语 + 语言选择，老用户直接进入主菜单."""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.callbacks import LangCallback
from bot.keyboards.inline import language_keyboard, main_menu_keyboard
from bot.models.user import Language

logger = logging.getLogger(__name__)
router = Router(name="start")

# 三语欢迎语
WELCOME_TEXT = (
    "👋 欢迎使用跨境电商客服机器人！\n"
    "请选择您的语言。\n\n"
    "👋 Welcome to Cross-border E-commerce Bot!\n"
    "Please select your language.\n\n"
    "👋 Добро пожаловать!\n"
    "Пожалуйста, выберите язык."
)

MENU_TITLES = {
    "zh": "📌 主菜单\n\n请选择您需要的服务：",
    "en": "📌 Main Menu\n\nPlease select a service:",
    "ru": "📌 Главное меню\n\nВыберите услугу:",
}


@router.message(CommandStart())
async def on_start(
    message: Message,
    lang: str = "zh",
    current_user: User | None = None,
) -> None:
    """处理 /start 命令."""
    if not message.from_user:
        return

    # UserMiddleware 已经负责了静默注册，如果 current_user 存在则说明连上了 DB
    if current_user and current_user.language:
        # 如果不是首次访问（或者系统有默认语言），直接进主菜单
        # 这里你可以增加逻辑判断是否为"真的是新"用户，例如通过 user.created_at
        lang = current_user.language.value

    # 对于明确发出 /start 命令的情况，我们统一展示语言选择键盘，以防用户想切语言
    await message.answer(
        WELCOME_TEXT,
        reply_markup=language_keyboard(),
    )


@router.callback_query(LangCallback.filter())
async def on_select_language(
    callback: CallbackQuery,
    callback_data: LangCallback,
    session: AsyncSession | None = None,
    current_user: User | None = None,
) -> None:
    """处理语言选择回调."""
    if not callback.from_user or not callback.message:
        return

    tg_user = callback.from_user
    lang_code = callback_data.code

    # 验证语言代码
    try:
        language = Language(lang_code)
    except ValueError:
        language = Language.ZH
        lang_code = "zh"

    # 有 DB 时保存用户语言信息
    if session and current_user:
        current_user.language = language
        await session.flush()

    # 编辑消息为主菜单
    await callback.message.edit_text(
        MENU_TITLES.get(lang_code, MENU_TITLES["zh"]),
        reply_markup=main_menu_keyboard(lang_code),
    )
    await callback.answer()

    logger.info("User %s selected language: %s", tg_user.id, lang_code)
