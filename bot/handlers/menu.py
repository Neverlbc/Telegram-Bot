"""主菜单导航 — 新版 3 按钮主菜单（+ 隐藏 VIP 入口）."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from bot.config import settings
from bot.keyboards.callbacks import MenuCallback, NavCallback
from bot.keyboards.inline import inventory_menu_keyboard, main_menu_keyboard, settings_menu_keyboard
from bot.services.hidden_access import (
    MENU_SERVICE_ADMIN,
    MENU_VANDYCH,
    MENU_VIP_INVENTORY,
    clear_state_keep_hidden_access,
    has_hidden_access,
)

logger = logging.getLogger(__name__)
router = Router(name="menu")

MENU_TITLES = {
    "zh": (
        "请选择功能模块：\n\n"
        "📦 莫斯科现货库存 — 仓库实时余量查询。\n"
        "🛠️ A-BF俄罗斯服务中心 — 维修进度跟踪以及和服务中心工程师直接对接。\n"
        "🧑‍🤝‍🧑 A-BF昼夜俱乐部 — 狩猎、战术、装备、自己人。\n\n"
        "🔐 战略合作伙伴 — 请输入专属访问码。"
    ),
    "en": (
        "Please choose a module:\n\n"
        "📦 Moscow Stock — real-time warehouse availability.\n"
        "🛠️ A-BF Russia Service Center — repair tracking &amp; direct contact with service engineers.\n"
        "🧑‍🤝‍🧑 A-BF Day and Night Club — hunting, tactics, gear, community.\n\n"
        "🔐 Strategic partners — enter your access code."
    ),
    "ru": (
        "Выберите нужный раздел:\n\n"
        "📦 Наличие в Москве — актуальные остатки со склада.\n"
        "🛠️ A-BF Россия Сервисный центр — отслеживание статуса ремонта и прямая связь с инженерами.\n"
        "🧑‍🤝‍🧑 A-BF Дневной и ночной клуб — охота, тактика, снаряжение, свои.\n\n"
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


def _expired_text(lang: str) -> str:
    return {
        "zh": "🔐 隐藏菜单访问已过期，请重新输入访问码。",
        "en": "🔐 Hidden menu access has expired. Please enter the access code again.",
        "ru": "🔐 Доступ к скрытому меню истёк. Введите код доступа ещё раз.",
    }.get(lang, "🔐 隐藏菜单访问已过期，请重新输入访问码。")


async def _hidden_menu_flags(state: FSMContext | None) -> dict[str, bool]:
    if not state:
        return {"vip_inventory": False, "service_admin": False, "vandych": False}
    return {
        "vip_inventory": await has_hidden_access(state, MENU_VIP_INVENTORY),
        "service_admin": await has_hidden_access(state, MENU_SERVICE_ADMIN),
        "vandych": await has_hidden_access(state, MENU_VANDYCH),
    }


async def _main_keyboard_with_hidden_access(
    lang: str,
    state: FSMContext | None,
) -> InlineKeyboardMarkup:
    flags = await _hidden_menu_flags(state)
    return main_menu_keyboard(
        lang,
        settings.club_tg_link,
        vip_inventory_unlocked=flags["vip_inventory"],
        service_admin_unlocked=flags["service_admin"],
        vandych_unlocked=flags["vandych"],
    )


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
        await clear_state_keep_hidden_access(state)

    target = callback_data.target

    if target == "settings":
        await callback.message.edit_text(
            SETTINGS_TITLES.get(lang, SETTINGS_TITLES["zh"]),
            reply_markup=settings_menu_keyboard(lang),
        )
    elif target == "inv_public":
        from bot.handlers.inventory import _t as inv_t
        vip_unlocked = bool(state and await has_hidden_access(state, MENU_VIP_INVENTORY))
        await callback.message.edit_text(
            inv_t(lang, "menu_title"),
            reply_markup=inventory_menu_keyboard(lang, vip_unlocked=vip_unlocked),
        )
    elif target == "inv_vip":
        from bot.handlers.inventory import _t as inv_t
        if not state or not await has_hidden_access(state, MENU_VIP_INVENTORY):
            await callback.message.edit_text(
                _menu_text(lang),
                reply_markup=main_menu_keyboard(lang, settings.club_tg_link),
            )
            await callback.answer(_expired_text(lang), show_alert=True)
            return
        await callback.message.edit_text(
            inv_t(lang, "menu_title"),
            reply_markup=inventory_menu_keyboard(lang, vip_unlocked=True),
        )
    elif target == "sc_menu":
        from bot.handlers.service_center import show_sc_menu
        admin_unlocked = bool(state and await has_hidden_access(state, MENU_SERVICE_ADMIN))
        await show_sc_menu(callback, lang, admin_unlocked=admin_unlocked)
    elif target == "sc_admin":
        if not state or not await has_hidden_access(state, MENU_SERVICE_ADMIN):
            from bot.handlers.service_center import show_sc_menu
            await show_sc_menu(callback, lang)
            await callback.answer(_expired_text(lang), show_alert=True)
            return
        from bot.handlers.service_center import show_sc_admin
        await show_sc_admin(callback, lang)
    else:
        # inv_public / inv_vip / menu / 其他 → 回主菜单
        await callback.message.edit_text(
            _menu_text(lang),
            reply_markup=await _main_keyboard_with_hidden_access(lang, state),
        )

    await callback.answer()
