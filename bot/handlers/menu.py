"""主菜单导航 — 新版 3 按钮主菜单（+ 隐藏 VIP 入口）."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.config import settings
from bot.keyboards.callbacks import MenuCallback, NavCallback
from bot.keyboards.inline import main_menu_keyboard, settings_menu_keyboard

logger = logging.getLogger(__name__)
router = Router(name="menu")

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

SETTINGS_TITLES = {
    "zh": "⚙️ <b>设置</b>",
    "en": "⚙️ <b>Settings</b>",
    "ru": "⚙️ <b>Настройки</b>",
}


def _menu_text(lang: str) -> str:
    return MENU_TITLES.get(lang, MENU_TITLES["zh"])


@router.message(Command("menu"))
async def on_menu_command(message: Message, lang: str = "zh", state: FSMContext | None = None) -> None:
    if state:
        await state.clear()
    await message.answer(
        _menu_text(lang),
        reply_markup=main_menu_keyboard(lang, settings.club_tg_link),
    )


@router.message(Command("cancel"))
async def on_cancel_command(message: Message, lang: str = "zh", state: FSMContext | None = None) -> None:
    if state:
        await state.clear()
    texts = {
        "zh": "❌ 已取消当前操作。",
        "en": "❌ Operation cancelled.",
        "ru": "❌ Операция отменена.",
    }
    await message.answer(texts.get(lang, texts["zh"]))
    await message.answer(
        _menu_text(lang),
        reply_markup=main_menu_keyboard(lang, settings.club_tg_link),
    )


@router.callback_query(MenuCallback.filter())
async def on_menu_action(
    callback: CallbackQuery,
    callback_data: MenuCallback,
    lang: str = "zh",
    state: FSMContext | None = None,
) -> None:
    if not callback.message:
        return
    action = callback_data.action

    if action == "settings":
        if state:
            await state.clear()
        await callback.message.edit_text(
            SETTINGS_TITLES.get(lang, SETTINGS_TITLES["zh"]),
            reply_markup=settings_menu_keyboard(lang),
        )
    elif action == "setting_lang":
        from bot.keyboards.inline import language_keyboard
        await callback.message.edit_text(
            "🌐 " + SETTINGS_TITLES.get(lang, SETTINGS_TITLES["zh"]),
            reply_markup=language_keyboard(),
        )
    await callback.answer()


@router.callback_query(NavCallback.filter(F.action == "home"))
async def on_nav_home(
    callback: CallbackQuery,
    lang: str = "zh",
    state: FSMContext | None = None,
) -> None:
    if not callback.message:
        return
    if state:
        await state.clear()
    await callback.message.edit_text(
        _menu_text(lang),
        reply_markup=main_menu_keyboard(lang, settings.club_tg_link),
    )
    await callback.answer()


@router.callback_query(NavCallback.filter(F.action == "back"))
async def on_nav_back(
    callback: CallbackQuery,
    callback_data: NavCallback,
    lang: str = "zh",
    state: FSMContext | None = None,
) -> None:
    """处理「返回上级菜单」按钮，统一路由所有 back 目标."""
    if not callback.message:
        return
    if state:
        await state.clear()

    target = callback_data.target

    if target == "settings":
        await callback.message.edit_text(
            SETTINGS_TITLES.get(lang, SETTINGS_TITLES["zh"]),
            reply_markup=settings_menu_keyboard(lang),
        )
    elif target == "sc_menu":
        from bot.handlers.service_center import show_sc_menu
        await show_sc_menu(callback, lang)
    elif target == "sc_admin":
        from bot.handlers.service_center import show_sc_admin
        await show_sc_admin(callback, lang)
    else:
        # inv_public / inv_vip / menu / 其他 → 回主菜单
        await callback.message.edit_text(
            _menu_text(lang),
            reply_markup=main_menu_keyboard(lang, settings.club_tg_link),
        )

    await callback.answer()
