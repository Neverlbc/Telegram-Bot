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
    "zh": "📌 <b>主菜单</b>\n\n请选择您需要的服务：",
    "en": "📌 <b>Main Menu</b>\n\nPlease select a service:",
    "ru": "📌 <b>Главное меню</b>\n\nВыберите услугу:",
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
    elif action == "profile":
        from bot.keyboards.inline import settings_menu_keyboard as smk
        user = callback.from_user
        if user:
            profile_text = {
                "zh": f"👤 <b>个人中心</b>\n\n用户名：@{user.username or '-'}\nID：<code>{user.id}</code>\n语言：{lang}",
                "en": f"👤 <b>Profile</b>\n\nUsername: @{user.username or '-'}\nID: <code>{user.id}</code>\nLanguage: {lang}",
                "ru": f"👤 <b>Профиль</b>\n\nПользователь: @{user.username or '-'}\nID: <code>{user.id}</code>\nЯзык: {lang}",
            }.get(lang, "")
        else:
            profile_text = "👤 Profile"
        await callback.message.edit_text(profile_text, reply_markup=smk(lang, show_profile=False))

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
