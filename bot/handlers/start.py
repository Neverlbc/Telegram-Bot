"""/start 命令 — 新用户欢迎语 + 语言选择，老用户直接进入主菜单."""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.keyboards.callbacks import LangCallback
from bot.keyboards.inline import language_keyboard, main_menu_keyboard
from bot.models.user import Language

logger = logging.getLogger(__name__)
router = Router(name="start")

# 三语欢迎语
WELCOME_TEXT = (
    "👋 欢迎使用官方 A-BF 助手机器人！\n\n"
    "您的私人助理，A-BF。请选择您的首选语言：\n\n"
    "我们随时为您服务。即使在黑暗中。\n\n"
    "👋 Welcome to the official A-BF assistant robot!\n\n"
    "Your personal assistant, A-BF. Please select your preferred language:\n\n"
    "We're always at your service. Even in the dark.\n\n"
    "👋 Добро пожаловать в официальный робот-помощник A-BF!\n\n"
    "Ваш персональный помощник A-BF. Пожалуйста, выберите предпочитаемый язык:\n\n"
    "Мы всегда к вашим услугам. Даже в темноте."
)

MENU_TITLES = {
    "zh": (
        "请选择功能模块：\n\n"
        "📦 莫斯科现货库存 — 仓库实时余量查询。\n"
        "🛠️ 服务中心 — 维修进度跟踪以及和服务中心工程师直接对接。\n"
        "🧑‍🤝‍🧑 A-BF 俱乐部 — 狩猎、战术、装备、自己人。\n\n"
        "🔐 战略合作伙伴 — 请输入专属访问码。"
    ),
    "en": (
        "Please choose a module:\n\n"
        "📦 Moscow Stock — real-time warehouse availability.\n"
        "🛠️ Service Center — repair tracking &amp; direct contact with service engineers.\n"
        "🧑‍🤝‍🧑 A-BF Club — hunting, tactics, gear, community.\n\n"
        "🔐 Strategic partners — enter your access code."
    ),
    "ru": (
        "Выберите нужный раздел:\n\n"
        "📦 Наличие в Москве — актуальные остатки со склада.\n"
        "🛠️ Сервис-центр — отслеживание статуса ремонта и прямая связь с инженерами.\n"
        "🧑‍🤝‍🧑 Клуб A-BF — охота, тактика, снаряжение, свои.\n\n"
        "🔐 Для стратегических партнёров — введите код доступа."
    ),
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
        reply_markup=main_menu_keyboard(lang_code, settings.club_tg_link),
    )
    await callback.answer()

    logger.info("User %s selected language: %s", tg_user.id, lang_code)
